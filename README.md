# STM — anticipating the severity of metro service incidents

## 1. Setup and execution with uv

Run the commands from the **project root**.

### Install uv

On Windows, in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Reopen the terminal if necessary, then check the installation:

```powershell
uv --version
```

Other installation methods are available in the [official uv documentation](https://docs.astral.sh/uv/getting-started/installation/).

### Prepare the environment

All required packages, **including development dependencies**, are already declared in `pyproject.toml`. Simply run:

```powershell
uv sync
```

This prepares `.venv` and installs the project dependencies, including `ipykernel`. Keep `pyproject.toml` and `uv.lock` for reproducibility. You do not need to activate `.venv` manually when using `uv run`.

Register the environment as a Jupyter kernel once on each machine:

```powershell
uv run python -m ipykernel install --user --name stm-challenge --display-name "Python (STM challenge)"
```

This creates a user-level kernelspec that VS Code and JupyterLab can discover. If you move the project to a different path, run this command again to refresh the kernelspec.

### Configure the data paths

The repository includes a `.env` file at the project root. Check that its paths match your local data files:

```dotenv
INCIDENTS_PATH=data/Incidents_metro.xls
KM_PATH=data/Kilometrage_metro_planifie.xls
```

Use the **exact names** of your data files when checking or updating these paths. Relative paths are resolved from the directory containing `.env`, even when the notebook is in `notebooks/`. The data therefore do not need to be moved into the notebook directory.

The supplied files contain **delimited text**, even when their extension is `.xls`: import them with `pandas.read_csv`, using `;` for incidents, `,` for mileage, and `utf-8-sig` encoding. Mileage values use a decimal comma. `read_excel` is not appropriate for these files.

### Open the notebooks

```powershell
uv run jupyter lab
```

Open **`notebooks/STM_Data_Pipeline.ipynb`**, select **Python (STM challenge)** as the kernel, and run the cells in order. Starting Jupyter does not automatically execute notebook cells. See the [uv and Jupyter guide](https://docs.astral.sh/uv/guides/integration/jupyter/).

Warnings are suppressed at the start of the notebook for readability. Explicit checks remain in place; temporarily disable suppression when investigating errors or convergence issues.

## 2. Project structure and reading order

| Directory or file | Purpose |
|---|---|
| `notebooks/STM_Data_Pipeline.ipynb` | **Main notebook to follow**: preparation, target, feature selection, models, thresholds, results and interpretation. |
| `notebooks/STM_Data_Exploration.ipynb` | All exploratory analysis: profiling, temporal coverage, distributions and consistency checks. Kept separate to make the pipeline easier to read. |
| `src/` | Functions used in the notebooks, centralized to avoid duplication and facilitate maintenance. |
| `data/` | Source tables and documentation, according to the paths configured in `.env`. |
| `.env` | Local paths to the two tables. |
| `pyproject.toml`, `uv.lock` | Dependencies and reproducible environment. |
| `README.md` | Methodology, decisions, results and limitations. |

The pipeline presents decisions and their consequences. The exploration notebook provides the supporting detail. Raw tables retain the original values.

## 3. Challenge, data and scope

The challenge aims to improve understanding of major incidents and inform business decisions. We focus on passenger-related operational concerns: **metro circulation, service interruptions and response speed**.

Two tables are available:

- **Incidents**: reported event, Train/Station type, initial symptom, causes established after analysis, line/location, times and duration class, and intervention information.
- **Planned mileage**: service budget by line, date, period and train run. It describes planned service supply, not actual distance travelled or ridership.

The dataset contains incidents, but no comparable set of **non-incident situations**. The problem addressed is therefore:

> **At the start of the service delay for a reported incident, predict whether it will cause a delay of at least 5 minutes, so the response can be adapted promptly.**

We do not predict whether or when an incident will occur. Creating “non-incidents” from dates absent from the file would assume that reporting is exhaustive and up to date. It would also raise questions about available predictors: an incident symptom or location cannot be arbitrarily imputed for these observations. The updates and publication delays described in the documentation reinforce this caution. Forecasting incidents before they occur would require a different dataset and a clear definition of observation units.

### Definition of a major incident

The documentation states that interruptions lasting **less than 5 minutes** are excluded from the indicators, following a benchmark of public transport industry best practices.

Our interpretation is: **an incident included in these indicators is considered important for operational monitoring**. We therefore use **at least 5 minutes** as a practical definition of a “major incident” for this exercise. This interprets a reporting threshold as a severity threshold; it is not a regulatory definition.

We assume that `Incident en minutes` represents this service delay. For trains, the documentation specifies that `Heure de l'incident` is the **start of the customer service delay**, not necessarily the physical onset of the incident; `Heure de reprise` marks its end.

A more precise business definition could incorporate duration, affected lines, passenger impact, safety and costs. It could lead to revising the target and alert levels. The duration threshold defining the target and the probability threshold triggering an alert are separate decisions.

## 4. Exploration and cleaning

Exploration examines types, missing values, frequent/rare categories, repeated records, distributions and shared coverage. It also compares recorded times with duration classes and reviews distributions by line, symptom and incident type.

### Types and missing values

Cleaning begins with conversions:

- calendar dates to dates; year, month, day and indicators such as CAT/Porte/KFS to numeric types;
- mileage to numeric values after replacing decimal commas;
- times to elapsed durations from the start of the service day, allowing values beyond 24 hours;
- identifiers retained as text.

Numeric or temporal values that cannot be converted become `NA`/`NaT`. In text columns, `#` becomes **“Pas d'évacuation”** in Évacuation and **“Aucune tournée associée”** in train run fields. Other markers (`#`, empty strings, `N/A`, etc.) become **“Inconnue”**. **“Non affecté” remains an explicit category**, not a missing value.

No incident is removed solely because a feature is missing. Imputation needed by the models is learned within training folds only. Symptoms are not imputed from subsequently established causes.

### Line and station/location

This distinction matters: location contributes information to the model, but inconsistent labels fragment categories.

- Colours become line numbers: green **1**, orange **2**, yellow **4**, blue **5**.
- Remove “Ligne”, deduplicate and sort: `Ligne 5, 1` becomes `1, 5`.
- Correct `02-avr` using the lines recorded in the secondary cause.
- Extract `Station` from `Code de lieu`, separating ` - Ligne …` suffixes while preserving hyphens within names.
- An unknown line may be completed from the location; “Non affecté” is not replaced.
- Remove `Code de lieu` from the cleaned table while preserving it in the raw table.

The `02-avr` correction relies on a cause determined after analysis. It is **neutralized in `Ligne_initiale` and derived predictors**, to prevent giving the model future information.

Cleaning is not an exhaustive validation against official station names. `Station` can still contain garages, sidings, composite locations and naming variants. Harmonizing these labels and distinguishing stations from technical facilities remain necessary before site-specific investment decisions.

### Calendar and duration

Add weekday (**Monday = 0**, Sunday = 6), Saturday/Sunday indicators and Quebec public holidays using `holidays` to both tables. This calendar does not replace the STM service calendar.

Calculate `Duree_calculee_minutes` by directly subtracting **service delay start from resumption time**. Extended times already account for the service-day convention: no automatic addition of 24 hours. Preserve the reported duration class rather than replacing it with the calculated duration.

Exploration showed that calculated duration and reported class do not always agree, particularly for **S** incidents assigned to “02 min et moins”. Their lack of impact on metro service may explain this operational classification, but **systematic assignment to this class is not established by the documentation**. We retain the discrepancy for auditing rather than automatically correcting duration.

### Retained scope

Exclude:

- **S**: the documentation states that station incidents do not affect metro service;
- **Non affecté**: we assume these concern technical facilities without an affected operating line. This does not mean every workshop or control centre incident is always without network consequences.

Of **45,561 incidents**, **16,491** are excluded, counting the overlap between the two criteria only once. **29,070 incidents** remain. `incidents_nettoyes_complets` retains all cleaned incidents before filtering.

### Mileage coverage and joining

Mileage covers **January 1, 2019 to September 30, 2023**, while incidents extend to **September 30, 2025**. The end of 2023 and the years 2024–2025 are not covered.

Check missing/negative values and repetitions by line/date/train run, then aggregate by line/date. The join does not multiply incidents. For multi-line events, sum mileage only when **all lines** are covered; otherwise retain a missing value, never zero.

We do not know why recent years are absent or whether service supply remained stable. **No extrapolation is applied.** A model variant nevertheless tests mileage's contribution over a shared period to assess whether further data collection would be worthwhile.

## 5. Target and feature selection

`Target_5min` is defined as follows:

| Value | Reported classes | Count |
|---|---|---:|
| 0 | Less than 5 minutes | 22,661 (77.95%) |
| 1 | At least 5 minutes | 6,409 (22.05%) |
| NA | Unknown/unrecognized class | 0 in the analysed files |

The classes are not equally distributed; no undersampling is performed. Major incident prevalence provides a reference for interpreting average precision.

Predictors must be available **at delay onset**: location, time, calendar and **symptom**, defined in the documentation as the initial cause assigned at the time of the incident.

Primary/secondary causes are excluded because they are determined after potentially lengthy analysis. Resumption, duration and duration class are excluded because they reveal the outcome. Intervention fields (evacuation, emergency response, CAT, etc.) are not retained without confirmation of initial availability. Identifiers, insufficiently documented features and redundant calendar variables remain outside this first version.

Time is represented by sine/cosine to respect its cyclic nature. Weekday makes Saturday/Sunday redundant. Two specifications are compared: **Line** or **Station**, with symptom, time and calendar in both.

### Redundancy and collinearity checks

- **Spearman** for numeric variables; **bias-corrected Cramér’s V** for categories.
- Group rare categories for diagnostics.
- Check **rank** and **VIF** after encoding: rank deficiency indicates exact dependence; a high VIF calls for examining stability.

Line, Station and number of lines share information. The initial specifications therefore separate Line and Station and remove the number of lines. Associations do not trigger automatic removal. Rare categories, separation, the form of numeric effects and influential observations remain points of attention; these diagnostics alone do not validate every assumption.

## 6. Modelling and validation strategy

### Why logistic regression?

Logistic regression provides an explainable baseline: probabilities/scores, coefficients and odds ratios support discussions with business stakeholders. The aim is to establish **what the available data can already support and what prevents further progress**, while assessing detection and error costs.

This choice is compatible with local computing resources. The incident volume and rarity of some categories favour controlled complexity and regularization; they do not establish that a complex model would necessarily perform poorly. A future comparison with other model families can assess the added value of greater complexity.

The “different models” tested here are **logistic regression variants**, not multiple algorithm families.

### With and without mileage

Compare the variants using **exactly the same covered incidents** and temporal split. The station model achieves AP of **0.3662 without mileage** versus **0.3658 with mileage**: no improvement over this first window.

This does not establish that mileage is always uninformative. However, it does not yet justify reconstructing missing years. The main model therefore proceeds **without mileage**, over the full period.

### Splitting without temporal leakage

The first 80% of dates are used for development; recent dates are reserved for testing. Development is then divided to separate fitting from threshold selection.

| Stage | Period | Incidents |
|---|---|---:|
| Parameter selection and fitting | January 1, 2019–April 26, 2023 | 18,074 |
| Finalist and threshold selection | April 27, 2023–May 25, 2024 | 4,937 |
| Reserved test | May 26, 2024–September 30, 2025 | 6,059 |

Check that the same incident does not appear in two periods. The test guides neither parameters nor threshold.

### Grid search

Temporal validation with **3 expanding folds** compares:

- location represented by Line or Station;
- L2 regularization, **C = 0.01 / 0.1 / 1 / 10**;
- class weights **none / balanced**, without changing the observations.

Imputation, standardization and encoding with rare-category grouping are learned within each fold. The encoder handles new categories. Reference categories are **Berri-UQAM** for Station and **Clientèle** for Symptom.

**Average precision** selects parameters for each specification. The two finalists are then compared on validation at the target recall, favouring fewer false positives. No refitting is performed after fixing the threshold, preserving the probabilities used to select it.

## 7. Alert objective and champion model

The priority is to detect as many major incidents as possible and adapt the response promptly. **Class 1 recall** measures this detection. However, false alarms can mobilize teams unnecessarily and be costly.

Without quantified costs, the selected trade-off is provisional: **achieve at least 90% recall on validation, then minimize false positives**. Scenarios at 80%, 90% and 95% make the trade-off visible. Alerting on every incident would achieve 100% recall without providing prioritization.

The champion is the **station-based** logistic regression, **C = 1**, **no class weighting**, with a probability threshold of **0.130476** selected on validation. At approximately 90% recall, it produces **2,937 false alarms** on validation, versus **3,053** for the line model.

### Results on the reserved test

| Metric | Result |
|---|---:|
| Major incident recall | **91.05%** |
| Alert precision | **26.55%** |
| Incidents triggering an alert | **79.70%** |
| Major incidents detected / missed | **1,282 / 126** |
| False alarms | **3,547** |
| Non-major incidents without an alert | **1,104** |
| Average precision | **0.3567** |
| ROC-AUC | **0.6570** |
| Brier score | **0.1688** |
| Major incident prevalence in the test | **23.24%** |

AP summarizes the precision-recall curve and differs from its trapezoidal integral. The confusion matrix and PR curve complement these metrics.

The model detects many major incidents, but nearly **four in five incidents** trigger an alert, and only **about one in four alerts** concerns a major incident. Prioritization remains limited. The default threshold of 0.5 would be unsuitable for the objective: it detects only one major incident in this test.

These results apply to the studied files and temporal split. They guarantee neither future stability nor economic benefit. When costs are known, select on validation using:

**Total cost = false-alarm cost × FP + missed-major-incident cost × FN**, potentially subject to operational capacity constraints.

## 8. Interpretation and investment opportunities

ORs are the exponentials of coefficients. They compare a category with its reference while holding the other model variables constant. **An OR of 2 does not necessarily double the probability.** Coefficients are penalized; no classical p-values or statistical confidence intervals are assigned. Tables are sorted by descending OR.

The **raw proportion** describes the observed share of major incidents in a category; the **OR** describes a conditional association in the model; the **major incident count** measures its operational volume. The three are complementary.

Permutation importance on validation mainly highlights **Symptom** (AP drop of approximately **0.085**) and **Station/location** (**0.068**). Time and calendar contribute less over this window. Permutations and correlations limit this interpretation; it is not a causal measure.

| Opportunity | Supporting results | Checks before investing |
|---|---|---|
| Quality of initial classification | Symptom has the largest predictive contribution. | Reporting reliability, training and benefits for anticipation. |
| Maintenance and technical response | OR ≈ **2.00** for Matériel roulant and **2.03** for Équipements fixes, vs Clientèle; **2,033 major incidents**, approximately **53%** of fitting-period major incidents. | Specific causes, affected assets, available actions and costs/benefits. |
| Passenger incident response | **1,469 major incidents**, the largest volume despite a proportion of **18.28%**. | Coordination and response delay. |
| Site diagnostics | Joliette: OR **2.76**, **75 major incidents**, proportion **36.23%**; Berri-UQAM: **171 major incidents**, proportion **13.63%**. | Location harmonization, ridership, exposure and intervention constraints. |
| Graduated alert response | **3,547 false positives** in the test. | Cost of lightweight confirmation followed by intervention, and team capacity. |

Some high ORs concern composite locations, such as Beaudry/Papineau (**3.80**), or nonspecific categories, such as Divers (**2.54**, only **77 incidents**). They support investigating data and mechanisms, not automatically undertaking works.

Final causes remain useful in a **separate retrospective analysis** to identify corrective actions. Predictive results do not establish that an intervention would reduce duration, and a duration-based target does not measure human or safety severity.

## 9. Limitations and next steps

### Challenge the assumptions and target

Validate the 5-minute threshold with stakeholders, its correspondence with service delay, the Non affecté scope and initial feature availability. Test 10/15-minute thresholds and severity definitions incorporating affected passengers, safety and incident type. A “rare severe event” category may require a distinct strategy: different events should not trigger identical efforts.

Consolidate location labels, then assess temporal stability, calibration and performance across multiple windows. The score should support a decision, not replace safety assessment.

### Collect the data needed for the next objective

- **Non-incident situations**: defined units (line/time slot, train/journey, etc.), exposure and confirmation of exhaustive recording. These would support studying prediction before occurrence and preventive preparation.
- **Traffic and ridership**: exposed passengers, connections, peak periods and areas where communication and interruptions have the greatest impact. Distinguish incident frequency, risk per unit of exposure and affected passenger volume.
- **Asset utilization**: actual mileage by trainset, age, maintenance and failure history. Planned mileage by line does not measure a trainset's wear.
- **Missing planning data**: STM sources for absent years and version histories, rather than unverified extrapolation.
- **Timeline and interventions**: information actually known at delay onset, available actions, mobilization times, effectiveness and cost of each response level.
- **Operational costs and passenger impact**: repairs, mobilization, lost service, costs of false positives and missed major incidents, and effects on satisfaction and trust.

Post-incident reviews, surveys and social media sentiment analysis can complement the study of passenger impact. However, they have selection and attribution biases and cannot alone quantify reputational cost.

### Determine the budget with stakeholders

First estimate operational and reputational costs and the consequences of errors. Then detail possible interventions, their cost and expected benefit. Finally compare alert strategies and allocate budget to actions with supported benefits, using experimentation or controlled evaluation.

The deliverable provides an explainable model, a measured alert trade-off and investigation opportunities. It particularly highlights the information needed to turn a predictive association into an economically viable operational decision.

## Sources

- Attached **Incidents du réseau du métro** documentation, City of Montreal / STM: scope, methodology and dictionary, pp. 1–5. [Official dataset page](https://donnees.montreal.ca/dataset/incidents-du-reseau-du-metro).
- Attached **Kilométrage métro des périodes de service** documentation, City of Montreal / STM: description, methodology and dictionary, pp. 1–3. [Official dataset page](https://donnees.montreal.ca/en/dataset/stm-kilometrage-metro-des-periodes-de-service).
- [uv installation](https://docs.astral.sh/uv/getting-started/installation/) and [Jupyter integration](https://docs.astral.sh/uv/guides/integration/jupyter/).
