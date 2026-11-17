# On-Demand Predictive Maintenance Application

## Overview

This application provides on-demand machine failure prediction using a trained MLflow model, FastAPI, and Streamlit.

Users can enter machine operating conditions through an interactive Streamlit interface and request a failure prediction from a FastAPI backend.

The application also includes a pair-plot visualization of the 8,000-observation training dataset, allowing users to explore relationships between operating conditions and historical machine failures.

## Architecture

The application uses the following architecture:

```text
             User
               |
               v
       Streamlit Interface
       (Machine Inputs)
               |
               v
          FastAPI
         /predict
               |
               v
       Input Validation
          (Pydantic)
               |
               v
       Feature Engineering
       (5 Additional Features)
               |
               v
       MLflow PyFunc Model
               |
               v
       Prediction Response
               |
               v
       Streamlit Results
```

The MLflow model is loaded once when FastAPI starts, rather than being loaded for every prediction request.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | Streamlit |
| Backend API | FastAPI |
| API server | Uvicorn |
| Model management | MLflow |
| Machine learning | Scikit-learn |
| Data processing | Pandas, NumPy |
| Visualization | Plotly |
| Data storage | Parquet |
| Input validation | Pydantic |

## Application Components

### 1. Streamlit Interface

`streamlit_app.py`

Provides the interactive user interface.

Features include:
- Machine type selection (L, M, H).
- Air temperature input.
- Process temperature input.
- Rotational speed input.
- Torque input.
- Tool wear input.
- On-demand failure prediction.
- Failure probability and binary classification results.
- Historical training-data pair plot.

### 2. FastAPI Backend

`fast_api_app.py`

Provides the prediction API.

The API:
- Loads the exported MLflow model during startup.
- Validates incoming requests.
- Calls the feature engineering pipeline.
- Performs model inference.
- Returns failure probability and predicted failure classification.

### 3. Input Validation

`schemas.py`

Defines the six original machine input variables and validates their types and acceptable values using Pydantic.

Machine type must be L, M, or H.

### 4. Feature Engineering

`feature_engineering.py`

The API accepts six original machine variables and calculates five additional features expected by the trained model.

| Engineered feature | Calculation |
|---|---|
| Mechanical_power_W | (2π / 60) × RPM × Torque |
| Temperature_difference_K | Process temperature − Air temperature |
| Torque_wear | Torque × Tool wear |
| Speed_wear | RPM × Tool wear |
| Power_wear | Mechanical power × Tool wear |

The resulting 11-column DataFrame follows the exact feature order expected by the exported MLflow model.

### 5. MLflow Model

The exported model is stored at:

`AWS_Fast_API_Streamlit_deployment/pm_hgb_model_export/`

FastAPI loads the model using:

`mlflow.pyfunc.load_model()`

The model artifact includes the MLflow model configuration, serialized Python model, and associated environment metadata.

### 6. Historical Training Data Visualization

The pair plot uses:

`data/plotting_data.parquet`

The visualization contains 8,000 training observations and five numerical operating variables:

- Air temperature
- Process temperature
- Rotational speed
- Torque
- Tool wear

Historical observations are displayed using their actual failure labels:

- Blue: No failure
- Red: Failure
- Black circle: Current machine inputs

The diagonal panels display normalized kernel density distributions for the two failure classes.

The visualization uses the full training-data range and does not modify the model's prediction inputs.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Checks API availability and model loading status |
| POST | `/predict` | Predicts machine failure probability and classification |
| GET | `/docs` | Interactive API documentation |

### Prediction request

The `/predict` endpoint accepts:

```json
{
  "Type": "M",
  "Air_temperature_K": 300.0,
  "Process_temperature_K": 310.0,
  "Rotational_speed_rpm": 1500,
  "Torque_Nm": 40.0,
  "Tool_wear_min": 120
}
```

### Prediction response

```json
{
  "failure_probability": 0.0125,
  "predicted_failure": 0
}
```

The values above illustrate the response structure, not a measured prediction.

## Installation

### Requirements

- Python 3.12
- pip
- Git

### 1. Clone the repository

```bash
git clone https://github.com/adebam/DataBricks_Predictive_Maintenance.git

cd DataBricks_Predictive_Maintenance
```

### 2. Create a virtual environment

```bash
cd apps/Predictive_Maintenance_on_demand

python3.12 -m venv .venv

source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip

python -m pip install -r requirements.txt
```

## Running the Application

The FastAPI backend and Streamlit frontend run in separate terminals.

### Terminal 1: Start FastAPI

From the application directory:

```bash
uvicorn fast_api_app:app \
  --host 127.0.0.1 \
  --port 8002
```

FastAPI loads the exported MLflow model during startup.

Check API health:

http://127.0.0.1:8002/health

Open interactive API documentation:

http://127.0.0.1:8002/docs

### Terminal 2: Start Streamlit

Activate the same virtual environment and navigate to the application directory:

```bash
cd apps/Predictive_Maintenance_on_demand

source .venv/bin/activate

streamlit run streamlit_app.py
```

Open the application:

http://localhost:8501

## Configuration

The application supports environment variables for model and API configuration.

| Variable | Default | Purpose |
|---|---|---|
| MODEL_PATH | Repository model export directory | Location of the MLflow model |
| API_URL | `http://127.0.0.1:8002` | FastAPI backend address |

For an alternative model location:

```bash
export MODEL_PATH="/absolute/path/to/pm_hgb_model_export"
```

For an alternative API address:

```bash
export API_URL="http://127.0.0.1:8002"
```

Set these variables in the appropriate terminal before starting the respective service.

## Project Structure

```text
DataBricks_Predictive_Maintenance/
│
├── AWS_Fast_API_Streamlit_deployment/
│   └── pm_hgb_model_export/
│       ├── MLmodel
│       ├── python_model.pkl
│       ├── requirements.txt
│       └── ...
│
├── apps/
│   └── Predictive_Maintenance_on_demand/
│       ├── data/
│       │   └── plotting_data.parquet
│       │
│       ├── fast_api_app.py
│       ├── feature_engineering.py
│       ├── schemas.py
│       ├── streamlit_app.py
│       ├── requirements.txt
│       └── README.md
│
└── README.md
```

## Scope and Limitations

This application demonstrates local, on-demand inference using a previously trained and exported MLflow model.

It is separate from the Databricks batch and streaming inference pipeline documented in the main project README.

The Streamlit pair plot presents historical training observations. It does not represent live incoming production data.

The default API configuration binds to localhost and is intended for local application use. A public deployment requires appropriate network, authentication, and service security configuration.

## Related Project

[Main Predictive Maintenance and Machine Failure Prediction Project](https://github.com/adebam/DataBricks_Predictive_Maintenance)

The main project covers the broader Databricks architecture, including data ingestion, Bronze/Silver/Gold processing, MLflow inference, prediction monitoring, drift detection, alerting, and CI/CD.
