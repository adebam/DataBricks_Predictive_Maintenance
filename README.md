# DatPredictive Maintenance and Machine Failure Prediction
##Project Overview

This project develops an end-to-end predictive maintenance workflow using Databricks. The objective is to identify machines at risk of failure from their operating conditions while building a data engineering and machine learning pipeline for a real-world industrial application.

The project combines data ingestion, data quality validation, exploratory data analysis, feature engineering, model training, threshold optimization, and dashboard development. It also incorporates a simulated streaming workflow to demonstrate how newly arriving machine data could be processed and scored after a model has been trained.

The project is being developed using the Databricks Lakehouse platform, with the aim of demonstrating practical skills in data engineering, machine learning, and operational deployment.

##Problem Statement

Unexpected machine failures can lead to unplanned downtime, increased maintenance costs, production losses, and equipment damage. Traditional maintenance strategies may rely on fixed schedules or respond only after a failure has occurred.

Predictive maintenance uses operating data to estimate the likelihood of equipment failure before it happens.

The central problem addressed in this project is:

**Can machine operating conditions be used to identify impending or likely machine failures while keeping false alarms at a manageable level?**

This is a binary classification problem in which the target variable, Machine_failure, indicates whether a machine failure has occurred.

Because failures are relatively rare, overall accuracy is not sufficient for evaluating the models. The evaluation therefore emphasizes recall, precision, the F2 score, and alert rate.

**Recall**: The proportion of actual failures identified by the model.

**Precision**: The proportion of predicted failures that are actual failures.

**F2 score**: A performance measure that gives recall more weight than precision.

**Alert rate**: The proportion of records flagged by the model.

The intended application prioritizes identifying failures while limiting unnecessary maintenance alerts.

