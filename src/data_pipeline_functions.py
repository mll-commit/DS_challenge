from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency
from sklearn.metrics import confusion_matrix, precision_recall_curve, precision_score, recall_score


DEFAULT_LINE_MAP = {"verte": "1", "orange": "2", "jaune": "4", "bleue": "5"}


def data_path(config, env_path, key):
    path = Path(config[key]).expanduser()
    return path if path.is_absolute() else env_path.parent / path


def numeric(series):
    return pd.to_numeric(series.str.replace(',', '.', regex=False), errors='coerce')


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value).casefold()) if unicodedata.category(c) != 'Mn')


def line_numbers(value, line_map=None):
    line_map = line_map or DEFAULT_LINE_MAP
    text = fold(value)
    if not (
        re.search(r'\blignes?\b', text)
        or any(re.search(rf'\b{color}\b', text) for color in line_map)
        or re.fullmatch(r'[1245\s,;/]+', text)
    ):
        return []
    numbers = set(re.findall(r'\b[1245]\b', text))
    numbers.update(number for color, number in line_map.items() if re.search(rf'\b{color}\b', text))
    return sorted(numbers, key=int)


def split_location(value, line_map=None):
    text = str(value).strip()
    if re.match(r'(?i)^lignes?\b', text):
        return 'Inconnue', line_numbers(text, line_map=line_map)
    parts = re.split(r'(?i)\s+-\s+(?=lignes?\b)', text, maxsplit=1)
    return parts[0], line_numbers(parts[1], line_map=line_map) if len(parts) == 2 else []


def normalize_line(line, secondary, location, line_map=None):
    if fold(line) == 'non affecte':
        return 'Non affecté'
    numbers = line_numbers(secondary, line_map=line_map) if fold(line) == '02-avr' else line_numbers(line, line_map=line_map)
    return ', '.join(numbers or location) or 'Inconnue'


def group_for_diagnostics(series, rare_category_threshold=30):
    values = series.astype('string').fillna('Inconnue')
    counts = values.value_counts()
    return values.where(values.map(counts).ge(rare_category_threshold), '__Rare categories__')


def cramers_v(x, y):
    table = pd.crosstab(x, y)
    n = table.to_numpy().sum()
    rows, cols = table.shape
    if n <= 1 or min(rows, cols) < 2:
        return np.nan
    chi2 = chi2_contingency(table, correction=False)[0]
    phi2 = max(0, chi2 / n - (rows - 1) * (cols - 1) / (n - 1))
    rows_corrected = rows - (rows - 1) ** 2 / (n - 1)
    cols_corrected = cols - (cols - 1) ** 2 / (n - 1)
    denominator = min(rows_corrected - 1, cols_corrected - 1)
    return np.sqrt(phi2 / denominator) if denominator > 0 else np.nan


def initial_features(table, columns, numeric_columns=None, unknown_label='Inconnue'):
    numeric_columns = set(numeric_columns or ['Hour_sin', 'Hour_cos'])
    x = table[columns].copy()
    for column in columns:
        if column in numeric_columns:
            x[column] = x[column].astype(float)
        else:
            x[column] = x[column].astype('string').fillna(unknown_label).astype(str)
    return x


def threshold_table(y_true, probabilities):
    precision_values, recall_values, thresholds = precision_recall_curve(y_true, probabilities)
    table = pd.DataFrame({'Threshold': thresholds, 'Precision': precision_values[:-1], 'Recall': recall_values[:-1]})
    negative_scores = np.sort(probabilities[np.asarray(y_true) == 0])
    table['False_alarms'] = len(negative_scores) - np.searchsorted(negative_scores, thresholds, side='left')
    return table


def choose_threshold(target_recall, table):
    eligible_thresholds = table.loc[table['Recall'].ge(target_recall)]
    return float(
        eligible_thresholds
        .sort_values(['False_alarms', 'Recall', 'Threshold'], ascending=[True, False, False])
        .iloc[0]['Threshold']
    )


def prediction_summary(y, p, threshold):
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        'Threshold': threshold,
        'Recall': recall_score(y, pred, zero_division=0),
        'Precision': precision_score(y, pred, zero_division=0),
        'Alert_rate': pred.mean(),
        'Major_detected_TP': int(tp),
        'Major_missed_FN': int(fn),
        'False_alarms_FP': int(fp),
        'Nonmajor_no_alert_TN': int(tn),
    }


def context_profile(table, column, target_col='Target_5min'):
    grouped = table.groupby(column, dropna=False)[target_col].agg(
        Incidents='size',
        Major_incidents='sum',
        Major_incident_proportion='mean',
    )
    grouped['Major_incident_proportion_pct'] = 100 * grouped.pop('Major_incident_proportion')
    return grouped
