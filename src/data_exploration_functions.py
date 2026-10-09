from pathlib import Path
import re

import pandas as pd


def resolve_data_path(config, env_path, project_root, variable_name):
    value = config.get(variable_name)
    if not value or not value.strip():
        raise ValueError(f'Set {variable_name} in {env_path}')

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()

    if not path.is_file():
        raise FileNotFoundError(f'File not found for {variable_name} : {path}')
    return path


def profile_table(df, date_cols=None, binary_cols=None, rare_threshold=5):
    date_cols = date_cols or DEFAULT_DATE_COLS
    binary_cols = binary_cols or DEFAULT_BINARY_COLS
    rows = []
    for column in df:
        series = df[column]
        values = series.value_counts(dropna=False)
        if column in date_cols:
            field_kind = 'Date/period'
        elif column in binary_cols:
            field_kind = 'Binary indicator'
        elif column == 'KM planifié':
            field_kind = 'Numeric value to convert'
        else:
            field_kind = 'Code/category/text to review'

        rows.append(
            {
                'column': column,
                'field_kind': field_kind,
                'imported_type': str(series.dtype),
                'pandas_missing': series.isna().sum(),
                'empty_or_whitespace': series.astype('string').str.strip().eq('').sum(),
                '#': series.eq('#').sum(),
                '#N/A': series.eq('#N/A').sum(),
                'Non affecté': series.eq('Non affecté').sum(),
                'category_count': series.nunique(dropna=False),
                f'rare_category_count_<={rare_threshold}': values.le(rare_threshold).sum(),
                'frequent_categories': str(values.head(5).to_dict()),
                'rare_examples': str(values[values.le(rare_threshold)].head(10).to_dict()),
            }
        )
    return pd.DataFrame(rows).set_index('column')


def normalize_run(series):
    cleaned = series.str.strip()
    numeric = pd.to_numeric(cleaned, errors='coerce')
    return numeric.map(lambda x: str(int(x)) if pd.notna(x) and x == int(x) else pd.NA)


def parse_lines(value, line_map=None):
    line_map = line_map or DEFAULT_LINE_MAP
    if value in line_map.values():
        return [value]
    text = str(value)
    return sorted(set(line_map[x] for x in re.findall(r'\b[1245]\b', text)))


def minutes(series):
    parts = series.str.extract(r'^(\d{1,2}):(\d{2})(?::\d{2})?$').apply(pd.to_numeric, errors='coerce')
    return (60 * parts[0] + parts[1]).where(parts[0].between(0, 23) & parts[1].between(0, 59))


def choose_day(series):
    values = sorted(set(series) - {'Non affecté', '#', ''})
    return values[0] if len(values) == 1 else ('Ambiguous' if len(values) > 1 else 'Non affecté')


def day_incident(series):
    values = set(series)
    return next(iter(values)) if len(values) == 1 else 'Multiple types'
