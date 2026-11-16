# Predictive Maintenance and Machine Failure Prediction

## Project overview

This project develops an end-to-end predictive maintenance workflow
using Databricks. The objective is to identify machines at risk of
failure from their operating conditions while demonstrating a practical
data engineering, machine learning, monitoring, and application
deployment architecture.

The project combines data ingestion, data quality validation,
exploratory analysis, feature engineering, model training, threshold
optimization, batch/streaming inference, prediction monitoring, feature
drift monitoring, alert generation, and dashboard development.

The intended application prioritizes identifying failures while keeping
unnecessary maintenance alerts manageable. Because failures are
relatively rare, overall accuracy is not sufficient for model
evaluation. The modeling workflow emphasizes recall, precision, F2
score, and alert rate.

## End-to-end solution

The project is organized into several connected components:

1.  **Data ingestion and processing:** landing data is ingested into
    Bronze, validated and transformed through Silver, and prepared in
    Gold.
2.  **Model development:** models are trained and evaluated, with
    threshold selection emphasizing high failure recall.
3.  **Inference:** incoming machine observations are scored using the
    registered MLflow model.
4.  **Monitoring:** prediction behavior and feature distributions are
    monitored over time.
5.  **Alerting:** drift events are evaluated and recorded for
    operational review.
6.  **Dashboard:** a Plotly Dash application presents predictions,
    drift, alerts, and pipeline status. It is hosted on AWS EC2 using
    Gunicorn and Nginx.

## CI/CD architecture

The repository currently has two separate delivery pipelines. They serve
different purposes and should not be treated as one deployment process.

### 1. Databricks DEV deployment

The Databricks Asset Bundle and its CI/CD workflow currently live on the
`feature/databricks-bundles` branch.

-   GitHub Actions runs Python tests and validates the Databricks DEV
    Asset Bundle.
-   On a push to `feature/databricks-bundles`, the workflow
    automatically deploys the bundle to the DEV Databricks workspace.
-   The bundle uses the `predictivemaintenance_dev` catalog.
-   The deployed resources include the landing-to-Bronze,
    Bronze-to-Silver, Silver-to-Gold, Gold-to-prediction,
    prediction-monitoring, and data-drift-monitoring jobs.
-   Bundle deployment updates job definitions; it does not automatically
    execute the jobs.

**Production Databricks deployment is not configured.** The current
Asset Bundle defines only a `dev` target. A separate manual production
workflow with approval gates is documented in [CI/CD Architecture and
Production Release
Design](Predictive_Maintenance/docs/05_CI_CD_Architecture_and_Production_Governance.md).

### 2. Dash deployment to AWS EC2

The Dash application is deployed separately from the Databricks jobs.

-   Dash CI runs dashboard syntax checks and tests for pull requests and
    pushes to `main`.
-   After an eligible successful Dash CI run on `main`, Dash CD assumes
    an AWS role through GitHub OIDC.
-   AWS Systems Manager sends the deployment command to the EC2
    instance.
-   The remote deployment checks the commit, working tree, service
    health, and fast-forward eligibility before updating the
    application.
-   It restarts the service, checks the application endpoint, and
    attempts to roll back if the update fails.

**The current EC2 deployment is automatic after eligible successful CI
runs on `main`.** It does not yet have a GitHub Environment approval
gate.

### Workflow inventory

  ---------------------------------------------------------------------
  Workflow                           Purpose
  ---------------------------------- ----------------------------------
  `databricks-ci.yml`                Tests, validates, and deploys the
                                     Databricks DEV Asset Bundle.
                                     Currently on
                                     `feature/databricks-bundles`.

  `dash-ci.yml`                      Tests the Dash application.

  `dash-deploy.yml`                  Deploys the tested Dash commit to
                                     AWS EC2 through OIDC and SSM.

  `aws-oidc-test.yml`                Manually tests AWS OIDC
                                     authentication.

  `aws-ssm-test.yml`                 Manually tests AWS Systems Manager
                                     connectivity.
  ---------------------------------------------------------------------

## Branch and release status

-   `main` is the repository's default branch and is currently used by
    the Dash CI/CD pipeline.
-   `feature/databricks-bundles` contains the Databricks Asset Bundle,
    Databricks CI workflow, and the reorganized notebook/job resources.
    This work has not yet been merged into `main`.
-   Databricks DEV deployment is automated; Databricks production
    deployment is not enabled.
-   Production deployment should require a reviewed change, a manual
    release action, and an approval gate.

## Security and deployment governance

The Dash deployment already includes useful safeguards such as OIDC
authentication, commit verification, clean-working-tree checks,
fast-forward-only updates, health checks, serialized deployments, and
rollback attempts.

The CI/CD review also identified controls that should be completed
before production Databricks deployment: branch protection, immutable
action pinning, verification of AWS and Databricks service-principal
permissions, separation of test and deployment roles, and a protected
production GitHub Environment.

See [CI/CD Architecture, Security Review, and Production Release
Design](Predictive_Maintenance/docs/05_CI_CD_Architecture_and_Production_Governance.md)
for the detailed workflow diagrams, security findings, and proposed
production release process.

## Project documentation

-   [Dataset and data
    ingestion](Predictive_Maintenance/docs/00_Dataset_and_data_ingestion.md)
-   [Machine failure model
    development](Predictive_Maintenance/docs/01_Machine_failure_Model_development.md)
-   [Streaming data
    architecture](Predictive_Maintenance/docs/02_Streaming_Data_Architecture.md)
-   [Prediction monitoring, drift, and
    alerts](Predictive_Maintenance/docs/03_Prediction_Monitoring_Drift_and_Alerts.md)
-   [Dashboard and AWS
    deployment](Predictive_Maintenance/docs/04_Dashboard_and_AWS_Deployment.md)
-   [CI/CD architecture and production
    governance](Predictive_Maintenance/docs/05_CI_CD_Architecture_and_Production_Governance.md)
