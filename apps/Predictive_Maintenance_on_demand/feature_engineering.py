
import math
import pandas as pd

from schemas import MachineInput


# Exact input order expected by the exported MLflow model
MODEL_INPUT_COLUMNS = [
    "Type",
    "Air_temperature_K",
    "Process_temperature_K",
    "Rotational_speed_rpm",
    "Torque_Nm",
    "Tool_wear_min",
    "Mechanical_power_W",
    "Temperature_difference_K",
    "Torque_wear",
    "Speed_wear",
    "Power_wear",
]


def build_model_input(machine: MachineInput) -> pd.DataFrame:
    """
    Accept six original machine variables and calculate
    the five engineered features expected by MLflow.
    """

    # Original variables
    machine_type = machine.Type
    air_temp = machine.Air_temperature_K
    process_temp = machine.Process_temperature_K
    rpm = machine.Rotational_speed_rpm
    torque = machine.Torque_Nm
    tool_wear = machine.Tool_wear_min

    # Engineered features
    mechanical_power = (
        (2 * math.pi / 60) * rpm * torque
    )

    temperature_difference = process_temp - air_temp

    torque_wear = torque * tool_wear

    speed_wear = rpm * tool_wear

    power_wear = mechanical_power * tool_wear

    # Construct the exact 11-column model input
    model_input = pd.DataFrame(
        [{
            "Type": machine_type,
            "Air_temperature_K": air_temp,
            "Process_temperature_K": process_temp,
            "Rotational_speed_rpm": rpm,
            "Torque_Nm": torque,
            "Tool_wear_min": tool_wear,
            "Mechanical_power_W": mechanical_power,
            "Temperature_difference_K": temperature_difference,
            "Torque_wear": torque_wear,
            "Speed_wear": speed_wear,
            "Power_wear": power_wear,
        }],
        columns=MODEL_INPUT_COLUMNS
    )

    return model_input
