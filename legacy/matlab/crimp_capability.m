clc; clear;
 
%% --- File selection (robust) ---
while true
    user_path = strtrim(input('Enter full path to Excel file (or press Enter to browse): ', 's'));
 
    if isempty(user_path)
        [file_name, folder_path] = uigetfile({'*.xlsx;*.xls', 'Excel Files (*.xlsx, *.xls)'}, ...
                                             'Select Crimp Data Excel File');
        if isequal(file_name,0), fprintf('No file selected. Try again.\n'); continue; end
        full_path = fullfile(folder_path, file_name);
 
    elseif isfolder(user_path)
        [file_name, folder_path] = uigetfile({'*.xlsx;*.xls', 'Excel Files (*.xlsx, *.xls)'}, ...
                                             'Select Crimp Data Excel File', user_path);
        if isequal(file_name,0), fprintf('No file selected. Try again.\n'); continue; end
        full_path = fullfile(folder_path, file_name);
 
    elseif isfile(user_path)
        full_path = user_path;
 
    else
        fprintf('Path not found: %s\n', user_path);
        continue;
    end
 
    [~,~,ext] = fileparts(full_path);
    if ~ismember(lower(ext), {'.xlsx','.xls'})
        fprintf('Selected file is not an Excel file: %s\n', full_path);
        continue;
    end
 
    fprintf('Reading: %s\n', full_path);
    break;
end
 
%% --- Read Excel file ---
data = readtable(full_path);
 
%% --- Show available columns FIRST ---
fprintf('\nAvailable columns in the selected file:\n');
for k = 1:numel(data.Properties.VariableNames)
    fprintf('  %2d) %s\n', k, data.Properties.VariableNames{k});
end
 
%% --- Ask user for Cavity column (name or index) ---
cavity_input = strtrim(input('\nEnter the column NAME or NUMBER for the Cavity: ', 's'));
cavity_col = resolve_column(cavity_input, data);
 
%% --- Ask user for Measurement column (name or index) ---
meas_input = strtrim(input('Enter the column NAME or NUMBER for the Measurement: ', 's'));
meas_col = resolve_column(meas_input, data);
 
% Validate/convert types
% Cavity -> categorical
if ~iscategorical(data.(cavity_col))
    try
        data.(cavity_col) = categorical(data.(cavity_col));
    catch
        error('Selected cavity column "%s" cannot be converted to categorical.', cavity_col);
    end
end
 
% Measurement -> numeric (try to coerce if needed)
if ~isnumeric(data.(meas_col))
    if iscellstr(data.(meas_col)) || isstring(data.(meas_col)) || iscategorical(data.(meas_col))
        data.(meas_col) = str2double(string(data.(meas_col)));
    else
        error('Selected measurement column "%s" is not numeric and cannot be converted.', meas_col);
    end
end
 
% Drop rows with missing values in either chosen column
data = rmmissing(data, 'DataVariables', {cavity_col, meas_col});
 
% Rename to standard internal names for the rest of the script
data.Cavity = data.(cavity_col);
data.Measurement = data.(meas_col);
 
fprintf('\nUsing columns -> Cavity: %s | Measurement: %s\n', cavity_col, meas_col);
 
%% --- THEN: Spec limits input (with validation loop) ---
while true
    USL = input('\nEnter the Upper Specification Limit (USL): ');
    LSL = input('Enter the Lower Specification Limit (LSL): ');
    if isnumeric(USL) && isnumeric(LSL) && isscalar(USL) && isscalar(USL) && USL > LSL
        break;
    else
        fprintf('Invalid spec limits. Ensure they are numeric scalars and USL > LSL. Try again.\n');
    end
end
 
%% --- Group and Initialize ---
cavities = categories(data.Cavity);
nCavities = numel(cavities);
residuals_all = [];
residuals_grouped = cell(nCavities,1);
cavity_stats = struct();
 
%% --- Process Each Cavity ---
for i = 1:nCavities
    cav = cavities{i};
    subset = data(data.Cavity == cav, :);
    y = subset.Measurement;
    mu = mean(y);
    sigma = std(y);
    residuals = y - mu;
 
    residuals_all = [residuals_all; residuals];
    residuals_grouped{i} = residuals;
 
    safe_cav = matlab.lang.makeValidName(char(cav));
    cavity_stats.(safe_cav).mean = mu;
    cavity_stats.(safe_cav).std  = sigma;
    cavity_stats.(safe_cav).n    = length(y);
end
 
%% --- Statistical Tests (Residual diagnostics) ---
[~, p_ad] = adtest(residuals_all);
group_labels = cell2mat(arrayfun(@(ii) repmat(ii, length(residuals_grouped{ii}), 1), ...
                                 (1:nCavities)', 'UniformOutput', false));
X = cell2mat(residuals_grouped);
p_levene = vartestn(X, group_labels, 'TestType', 'LeveneAbsolute', 'Display', 'off');
 
%% --- One-way ANOVA (Means comparison across cavities) ---
[p_anova, tbl_anova, stats_anova] = anova1(data.Measurement, data.Cavity, 'off');
 
fprintf('\n--- Statistical Test Results ---\n');
fprintf('Anderson-Darling Normality (residuals) P-Value: %.4f -> %s\n', p_ad,     passfail(p_ad));
fprintf('Levene''s Homoscedasticity (residuals) P-Value: %.4f -> %s\n', p_levene, passfail(p_levene));
fprintf('One-way ANOVA (means by cavity) P-Value: %.4f -> %s\n', p_anova, passfail(p_anova));
 
%% --- Plot: Normality of Residuals ---
figure('Name','Normality of Residuals');
subplot(1,2,1)
histogram(residuals_all, 20, 'Normalization', 'pdf')
hold on
x_vals = linspace(min(residuals_all), max(residuals_all), 100);
plot(x_vals, normpdf(x_vals, mean(residuals_all), std(residuals_all)), 'r', 'LineWidth', 2)
title('Histogram + Normal Curve'); xlabel('Residuals'); ylabel('Density'); grid on; hold off;
 
subplot(1,2,2)
qqplot(residuals_all); title('Q-Q Plot of Residuals'); grid on;
 
%% --- Plot: Homoscedasticity Check (Boxplot) ---
figure('Name','Homoscedasticity Check');
boxplot(data.Measurement, data.Cavity)
xlabel('Cavity'); ylabel('Measurement');
title('Boxplot of Measurement by Cavity'); grid on;
 
%% --- Plot: Observations vs Residuals (Color-coded) ---
figure('Name','Observations vs Residuals'); hold on
colors = lines(nCavities); startIdx = 1;
for i = 1:nCavities
    r = residuals_grouped{i};
    plot(startIdx:startIdx+length(r)-1, r, 'o-', 'Color', colors(i,:), 'MarkerSize', 3)
    startIdx = startIdx + length(r);
end
xlabel('Observation Index'); ylabel('Residual');
title('Observations vs. Residuals'); grid on;
 
%% --- Plot: Cavity Means with 95% Confidence Intervals ---
means   = zeros(nCavities,1);
ns      = zeros(nCavities,1);
sems    = zeros(nCavities,1);
tcrit   = zeros(nCavities,1);
cihalf  = zeros(nCavities,1);
 
for i = 1:nCavities
    y = data.Measurement(data.Cavity == cavities{i});
    y = y(~isnan(y));
    ns(i)     = numel(y);
    means(i)  = mean(y);
    sems(i)   = std(y) / sqrt(max(ns(i),1));
    tcrit(i)  = tinv(0.975, max(ns(i)-1,1));
    cihalf(i) = tcrit(i) * sems(i);
end
 
figure('Name','Cavity Means with 95% CI');
errorbar(1:nCavities, means, cihalf, 'o-', 'LineWidth', 1.2, 'MarkerSize', 6);
xlim([0.5, nCavities+0.5]); grid on;
set(gca, 'XTick', 1:nCavities, 'XTickLabel', string(cavities), 'XTickLabelRotation', 0);
xlabel('Cavity'); ylabel('Mean Measurement');
title('Cavity Means with 95% Confidence Intervals');
 
%% --- Post-hoc: Tukey-Kramer multiple comparisons (if ANOVA significant) ---
if p_anova < 0.05
    figure('Name','Tukey-Kramer Multiple Comparisons');
    multcompare(stats_anova, 'CType','tukey-kramer');
end
 
%% --- Capability Analysis ---
if p_ad > 0.05 && p_levene > 0.05
    % Pooled Std Dev
    num = 0; denom = 0;
    for i = 1:nCavities
        cav = matlab.lang.makeValidName(char(cavities{i}));
        n = cavity_stats.(cav).n;
        s = cavity_stats.(cav).std;
        num = num + (n - 1) * s^2;
        denom = denom + (n - 1);
    end
    pooled_std = sqrt(num / denom);
    fprintf('\nPooled Standard Deviation: %.4f\n', pooled_std);
 
    % Capability Table
    cap_table = table(cavities, zeros(nCavities,1), zeros(nCavities,1), zeros(nCavities,1), zeros(nCavities,1), ...
        'VariableNames', {'Cavity','Mean','Cp','Cpk','DPM'});
 
    for i = 1:nCavities
        cav_raw = cavities{i};
        cav = matlab.lang.makeValidName(char(cav_raw));
        mu = cavity_stats.(cav).mean;
        cap_table.Mean(i) = mu;
        [cp, cpk] = calc_capability(mu, pooled_std, USL, LSL);
        dpm = calc_dpm(cpk);
        cap_table.Cp(i) = cp;
        cap_table.Cpk(i) = cpk;
        cap_table.DPM(i) = dpm;
    end
 
    fprintf('\n--- Final Capability Summary ---\n');
    disp(cap_table);
 
    % Average DPM -> DPMO -> Overall Cpk
    avg_dpm = mean(cap_table.DPM);
    overall_cpk = calc_cpk_from_dpm(avg_dpm);
    fprintf('\nDPMO (Average DPM): %.2f\n', avg_dpm);
    fprintf('Equivalent Overall Cpk: %.4f\n', overall_cpk);
 
    if overall_cpk > 1.8
        fprintf('\n🎉 Whoohoo! This is a great process 🎉\n');
    end
 
    % Export to Excel
    results_folder = fullfile(fileparts(full_path), 'Results');
    if ~exist(results_folder, 'dir')
        mkdir(results_folder);
    end
    output_file = fullfile(results_folder, 'Capability_Results.xlsx');
    writetable(cap_table, output_file);
else
    fprintf('\nCapability analysis skipped: Assumptions not met.\n');
end
 
%% --- Utility Functions ---
function colname = resolve_column(user_text, T)
% Resolve a column from name or index string; return column variable name
    varNames = T.Properties.VariableNames;
    idx = str2double(user_text);
    if ~isnan(idx) && isfinite(idx) && round(idx)==idx ...
&& idx >= 1 && idx <= numel(varNames)
        colname = varNames{idx};
        return;
    end
    if ismember(user_text, varNames)
        colname = user_text;
        return;
    end
    ci = find(strcmpi(user_text, varNames), 1);
    if ~isempty(ci)
        colname = varNames{ci};
        return;
    end
    error('Column "%s" not found. Please check the name or index.', user_text);
end
 
function [cp, cpk] = calc_capability(mu, sigma, usl, lsl)
    cp  = (usl - lsl) / (6 * sigma);
    cpu = (usl - mu)  / (3 * sigma);
    cpl = (mu - lsl)  / (3 * sigma);
    cpk = min(cpu, cpl);
end
 
function dpm = calc_dpm(cpk)
    z = cpk * 3;
    p = 2 * (1 - normcdf(z));
    dpm = p * 1e6;
end
 
function cpk = calc_cpk_from_dpm(dpm)
    p = dpm / 1e6;
    z = norminv(1 - p/2);
    cpk = z / 3;
end
 
function result = passfail(p)
    if p > 0.05
        result = 'PASS';
    else
        result = 'FAIL';
    end
end