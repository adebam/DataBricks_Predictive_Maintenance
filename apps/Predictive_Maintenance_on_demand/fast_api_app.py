###########################################
#
#         Design POST REQUEST
#
###########################################
import uvicorn

import os
import logging

from pathlib import Path
from contextlib import asynccontextmanager

import mlflow.pyfunc
import pandas as pd

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from schemas import MachineInput
from feature_engineering import build_model_input


# ============================================================
# CONFIGURATION
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MODEL_PATH = (
    REPO_ROOT
    / "AWS_Fast_API_Streamlit_deployment"
    / "pm_hgb_model_export"
)

MODEL_PATH = Path(
    os.getenv("MODEL_PATH", str(DEFAULT_MODEL_PATH))
).expanduser()

print("Model path:", MODEL_PATH)
print("Model directory exists:", MODEL_PATH.exists())

# --------------------------------------------------
# Response schemas
# --------------------------------------------------
class PredictionResult(BaseModel):
    failure_probability: float
    predicted_failure: int

# ============================================================
# Load model once at startup
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Loading model from: %s", MODEL_PATH)

    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"Model directory not found: {MODEL_PATH}"
        )

    try:
        app.state.model = mlflow.pyfunc.load_model(
            str(MODEL_PATH)
        )

        logger.info("MLflow model loaded successfully")

    except Exception:
        logger.exception("Model loading failed")
        raise

    yield

    logger.info("FastAPI shutting down")


app = FastAPI(
    title="Predictive Maintenance API",
    description="On-demand machine failure prediction",
    version="1.0.0",
    lifespan=lifespan
)

# ============================================================
# Health endpoint
# ============================================================
@app.get("/health")
def health(request: Request):

    model_loaded = (
        getattr(request.app.state, "model", None)
        is not None
    )

    return {
        "status": "healthy" if model_loaded else "not_ready",
        "model_loaded": model_loaded
    }

# ============================================================
# Single machine prediction
# ============================================================
@app.post("/predict",response_model=PredictionResult)
def predict(machine: MachineInput,request: Request):

    try:

        # Retrieve already-loaded model
        model = request.app.state.model

        # Calculate five engineered features
        model_input = build_model_input(machine)

        # Run MLflow inference
        output = model.predict(model_input)

        result = output.iloc[0]

        return PredictionResult(
            failure_probability=float(
                result["failure_probability"]
            ),
            predicted_failure=int(
                result["predicted_failure"]
            )
        )

    except Exception:

        logger.exception("Prediction failed")

        raise HTTPException(
            status_code=500,
            detail="Prediction failed. Check API logs."
        )
  
 # connects fast api to streamlit   
if __name__=="__main__":
    uvicorn.run(app="fast_api_app:app", port=8002, reload=True, host="127.0.0.1")