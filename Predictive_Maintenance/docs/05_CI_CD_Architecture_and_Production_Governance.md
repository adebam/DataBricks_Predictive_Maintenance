# CI/CD Architecture, Security Review, and Production Release Design

**Review date:** 16 November 2026\
**Repository:**
[adebam/DataBricks_Predictive_Maintenance](https://github.com/adebam/DataBricks_Predictive_Maintenance)

## 1. Executive summary

The project now has two distinct delivery paths:

1.  **Databricks DEV:** changes on `feature/databricks-bundles` are
    tested, the DEV Asset Bundle is validated, and the bundle is
    automatically deployed to the DEV Databricks environment.
2.  **Dash on AWS EC2:** changes to the dashboard on `main` are tested.
    A successful Dash CI run can trigger deployment to the live EC2 host
    through GitHub OIDC and AWS Systems Manager (SSM).

These are separate pipelines. Deploying Databricks job definitions is
not the same operation as running those jobs, and neither operation
should be confused with deploying the Dash web application.

**Production Databricks deployment is not configured.** The Asset Bundle
currently defines only the `dev` target. A separate, manually initiated
and approval-gated production process is proposed below; it is not
enabled by this documentation change.

## 2. Current branch and environment state

  ---------------------------------------------------------------------
  Item                               Current state
  ---------------------------------- ----------------------------------
  Default branch                     `main`

  Databricks development branch      `feature/databricks-bundles`

  Databricks Asset Bundle            Present on
                                     `feature/databricks-bundles`; not
                                     yet merged into `main`

  DEV catalog                        `predictivemaintenance_dev`

  Existing production catalog        `predictivemaintenancecatalog`

  Bundle targets                     `dev` only

  Databricks production workflow     Not created

  Dash hosting                       AWS EC2, deployed from `main`

  Branch protection                  Neither branch currently reports
                                     as protected; no repository
                                     rulesets were returned during
                                     review
  ---------------------------------------------------------------------

This README and governance document should be added to both branches so
the default-branch landing page can describe the active development
pipeline. The Databricks workflow and bundle configuration are currently
available on the feature branch.

## 3. Current CI/CD architecture

``` mermaid
flowchart TB
    subgraph DB["Databricks development delivery"]
        F["feature/databricks-bundles"]
        DCI["Databricks CI<br/>pytest + bundle validation"]
        DEV["Deploy Asset Bundle<br/>target: dev"]
        CAT["DEV workspace and catalog<br/>predictivemaintenance_dev"]
        F --> DCI --> DEV --> CAT
    end

    subgraph DASH["Dash EC2 delivery"]
        M["main"]
        CI["Dash CI<br/>syntax checks + pytest"]
        CD["Dash CD<br/>successful CI on main"]
        OIDC["GitHub OIDC<br/>assume AWS role"]
        SSM["AWS Systems Manager"]
        EC2["EC2<br/>Git fast-forward, compile,<br/>restart, health check, rollback"]
        M --> CI --> CD --> OIDC --> SSM --> EC2
    end

    F -. "future reviewed promotion" .-> M
```

The dotted promotion line is a proposed release path, not an automated
promotion currently configured in the repository.

## 4. Workflow inventory

  -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  Workflow or configuration                                                                                                              Trigger and purpose            Deployment behavior
  -------------------------------------------------------------------------------------------------------------------------------------- ------------------------------ -------------------------------
  [Databricks                                                                                                                            Pushes affecting Databricks    Runs tests and DEV bundle
  CI](https://github.com/adebam/DataBricks_Predictive_Maintenance/blob/feature/databricks-bundles/.github/workflows/databricks-ci.yml)   bundle files on                validation. Automatically
                                                                                                                                         `feature/databricks-bundles`   deploys the bundle to DEV only
                                                                                                                                         or `main`; pull requests       for a push to
                                                                                                                                         targeting `main`; manual       `feature/databricks-bundles`.
                                                                                                                                         dispatch                       

  [Dash CI](../../.github/workflows/dash-ci.yml)                                                                                         Pull requests targeting        Installs dashboard
                                                                                                                                         `main`, pushes to `main`, or   dependencies, checks Python
                                                                                                                                         manual dispatch                syntax, and runs dashboard
                                                                                                                                                                        tests in demo mode.

  [Dash CD](../../.github/workflows/dash-deploy.yml)                                                                                     A completed Dash CI workflow   On successful eligible CI runs,
                                                                                                                                         on `main`                      assumes the AWS role through
                                                                                                                                                                        OIDC and deploys the tested
                                                                                                                                                                        commit to EC2 through SSM. This
                                                                                                                                                                        currently runs automatically;
                                                                                                                                                                        it has no GitHub environment
                                                                                                                                                                        approval gate in the workflow.

  [AWS OIDC test](../../.github/workflows/aws-oidc-test.yml)                                                                             Manual dispatch                Verifies AWS identity
                                                                                                                                                                        federation.

  [AWS SSM test](../../.github/workflows/aws-ssm-test.yml)                                                                               Manual dispatch                Tests SSM connectivity to EC2.
                                                                                                                                                                        The command currently issued is
                                                                                                                                                                        read-only, but the workflow
                                                                                                                                                                        uses the deployment role.

  [Databricks Asset Bundle                                                                                                               Defines bundle targets,        Currently defines the DEV
  configuration](https://github.com/adebam/DataBricks_Predictive_Maintenance/blob/feature/databricks-bundles/databricks.yml)             workspace location, and        target only.
                                                                                                                                         catalog selection              

  [Databricks job resources](https://github.com/adebam/DataBricks_Predictive_Maintenance/tree/feature/databricks-bundles/resources)      Defines the Lakeflow Job       Job definitions receive the
                                                                                                                                         resources                      target catalog and deployment
                                                                                                                                                                        target as parameters.
  -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

### 4.1 Databricks DEV delivery

The Databricks CI workflow performs these steps:

1.  Checks out the repository.
2.  Sets up Python 3.12 and installs `requirements-test.txt`.
3.  Runs the notebook-format, notebook-syntax, and bundle-reference
    tests.
4.  Installs the Databricks CLI.
5.  Authenticates using Databricks OAuth machine-to-machine credentials.
6.  Validates the DEV Asset Bundle.
7.  Checks the existing DEV bundle deployment state.
8.  On a push to `feature/databricks-bundles`, deploys the DEV bundle
    and retrieves its summary.

The workflow uses `contents: read` permissions. Authentication and
bundle operations are skipped for pull requests from external forks so
those pull requests do not receive the Databricks secrets.

The DEV target defaults to `predictivemaintenance_dev`. The job
resources pass the selected catalog and bundle target to the notebooks.
Each configured Lakeflow job also limits itself to one concurrent run.

A successful bundle deployment updates the managed job resources and
workspace files. It does **not** automatically execute the ingestion,
prediction, or monitoring jobs.

### 4.2 Dash EC2 delivery

The Dash workflow is separate from Databricks bundle deployment:

1.  Dash CI runs the dashboard tests.
2.  Dash CD listens for completion of Dash CI on `main`.
3.  It proceeds only when the CI conclusion is successful, the source
    branch is `main`, and the run belongs to this repository.
4.  GitHub obtains short-lived AWS credentials through OIDC.
5.  The workflow sends a deployment command to the EC2 instance using
    AWS Systems Manager.
6.  The remote script checks the commit SHA, branch, clean working tree,
    existing service health, and fast-forward eligibility.
7.  It compiles the application, restarts the service, and checks the
    local HTTP endpoint.
8.  If the application update fails, it attempts to restore the previous
    commit and restart the previous version.

The deployment workflow also serializes deployments and refuses to
deploy when dashboard dependencies have changed, requiring a separately
reviewed environment update.

**Important:** Dash CD currently deploys automatically after a
successful eligible Dash CI run on `main`. A manual run of Dash CI on
`main` is also an eligible event. The workflow does not currently
reference a GitHub Environment that would pause deployment for approval.

## 5. Security and deployment safeguards review

### 5.1 Controls already in place

  ------------------------------------------------------------------------
  Area                 Existing control               Assessment
  -------------------- ------------------------------ --------------------
  Databricks workflow  `contents: read`               Good least-privilege
  permissions                                         starting point.

  Fork pull requests   Databricks authentication      Prevents Databricks
                       steps are skipped for external secrets from being
                       forks                          exposed to fork PR
                                                      jobs.

  DEV isolation        DEV deployment is limited to   Good separation for
                       pushes on                      current development
                       `feature/databricks-bundles`   work.
                       and uses the DEV               
                       target/catalog                 

  AWS authentication   OIDC federation instead of     Good approach; the
                       long-lived AWS access keys in  IAM trust policy
                       GitHub                         still needs
                                                      independent
                                                      verification.

  AWS account          Deployment action specifies    Helps prevent
  restriction          the expected AWS account ID    credentials being
                                                      used against an
                                                      unintended account.

  Deployment identity  Dash CD is restricted to       Good source and
                       successful CI runs on `main`   success checks.
                       from this repository           

  Deployment           EC2 verifies the requested SHA Prevents stale
  consistency          is still the current remote    deployments.
                       `main` commit                  

  Host safety          Clean working tree, expected   Good fail-closed
                       branch, fast-forward-only      safeguards.
                       update, and existing-service   
                       health check                   

  Recovery             Post-restart health check and  Good baseline
                       rollback attempt               recovery mechanism.

  Concurrent EC2       A deployment concurrency group Good.
  releases             prevents overlapping Dash      
                       deployments                    
  ------------------------------------------------------------------------

### 5.2 Findings to address

  --------------------------------------------------------------------------
  Priority             Finding                        Risk and recommended
                                                      action
  -------------------- ------------------------------ ----------------------
  **High**             `main` and                     A direct push can
                       `feature/databricks-bundles`   bypass pull-request
                       are not protected, and no      review and required
                       repository rulesets were       checks. Configure
                       returned                       branch rules requiring
                                                      pull requests and
                                                      successful CI checks.

  **High**             Dash EC2 CD has no approval    A successful Dash CI
                       gate                           run on `main`
                                                      automatically triggers
                                                      the live EC2
                                                      deployment. Add a
                                                      protected GitHub
                                                      Environment with
                                                      required reviewers
                                                      before treating this
                                                      as a manually
                                                      controlled production
                                                      release.

  **High**             AWS SSM test workflow uses the Its current command is
                       same role as Dash deployment   read-only, but
                                                      permission to invoke
                                                      `AWS-RunShellScript`
                                                      can be powerful. Use a
                                                      separate restricted
                                                      test role or retire
                                                      the test workflow
                                                      after validation.

  **Medium**           Some GitHub Actions are        Pin third-party
                       referenced by mutable tags,    actions to verified
                       including                      full commit SHAs. Keep
                       `databricks/setup-cli@main`    the Databricks CLI
                                                      version explicitly
                                                      pinned and update
                                                      action SHAs through
                                                      reviewed changes.

  **Medium**           Databricks deployment has no   Concurrent bundle
                       explicit GitHub Actions        deployments could
                       concurrency group              overlap. Add a DEV
                                                      deployment concurrency
                                                      group before
                                                      increasing automation.

  **Medium**           AWS OIDC trust and IAM         Inspect AWS IAM
                       permission policies cannot be  directly. Restrict the
                       verified from repository files OIDC audience and
                                                      subject to the
                                                      intended repository,
                                                      branch, and/or GitHub
                                                      Environment. Limit SSM
                                                      permissions to the
                                                      required instance and
                                                      commands.

  **Medium**           Databricks service-principal   Confirm the current CI
                       privileges cannot be verified  identity can manage
                       from repository files          only the DEV workspace
                                                      resources and DEV
                                                      catalog. Production
                                                      must use a separate
                                                      identity.

  **Medium**           Production Databricks target   Do not add production
                       and credentials are not        credentials to the
                       configured                     current DEV workflow.
                                                      Create a separate
                                                      target, identity,
                                                      secrets, and
                                                      approval-gated
                                                      workflow.
  --------------------------------------------------------------------------

The branch-protection status was read from the repository's branch
metadata and ruleset listing. The repository review does not provide
access to the AWS IAM role trust policy, AWS permission policy, or all
GitHub Environment protection settings; those must be checked in their
respective consoles.

## 6. Proposed Databricks production deployment process

Production deployment should be a separate release workflow. It should
not be an extension of the automatic DEV deployment job.

### 6.1 Proposed promotion path

1.  **Develop on `feature/databricks-bundles`.** Pushes run tests,
    validate the bundle, and deploy only to DEV.
2.  **Verify in DEV.** Run the ingestion, prediction, monitoring, and
    drift jobs against DEV data. Review outputs and alerts.
3.  **Open a pull request to `main`.** Require successful CI and a
    review before merging.
4.  **Merge to `main`.** Merging does not itself deploy the Databricks
    production bundle.
5.  **Manually start the production deployment workflow.** It must run
    from `main` and deploy the exact reviewed commit.
6.  **Require production approval.** The deployment job uses a protected
    GitHub Environment with required reviewers. Production credentials
    are available only to the approved deployment job.
7.  **Validate and deploy.** Validate the production target, confirm the
    intended workspace and catalog, then deploy the bundle.
8.  **Verify the deployment.** Check the bundle summary and deployed job
    definitions. Run only explicitly approved smoke tests.
9.  **Run production data jobs separately.** Deployment of job
    definitions must not automatically trigger ingestion, prediction, or
    monitoring jobs.

### 6.2 Production environment separation

The future production target should use:

-   **Catalog:** `predictivemaintenancecatalog`.
-   **A distinct bundle workspace root:** separate from the DEV bundle
    state.
-   **A dedicated production service principal:** separate from the
    identity used by DEV CI.
-   **Separate GitHub production secrets and variables:** for example,
    production-specific Databricks host, client ID, and client secret.
-   **A production GitHub Environment:** configured with required
    reviewers and deployment-branch restrictions.
-   **Production Unity Catalog grants:** limited to the schemas and
    tables the production jobs actually need.

The existing DEV target should remain the default. Production should
never become the default target for an ordinary CI run.

### 6.3 Proposed production workflow controls

A future workflow, for example
`.github/workflows/databricks-prod-deploy.yml`, should:

-   Use `workflow_dispatch` rather than deploying automatically on every
    push.
-   Refuse to run from a branch other than `main`.
-   Run the required tests and production bundle validation before
    deployment.
-   Use a production-specific GitHub Environment with required reviewer
    approval.
-   Obtain production credentials only inside the approved deployment
    job.
-   Use a concurrency group so only one production bundle deployment
    runs at a time.
-   Deploy the same commit that passed validation and was approved.
-   Run `databricks bundle deploy -t prod` and record the resulting
    bundle summary.
-   Avoid `bundle destroy`, destructive cleanup, or automatic execution
    of production jobs.
-   Record the deployed commit SHA and provide a documented rollback
    path to the previous known-good bundle version.

The deployment workflow should manage job definitions and workspace
resources. Production job execution and data-changing operations should
have their own operational controls.

### 6.4 Rollback approach

For a failed bundle release, redeploy the previous known-good Git commit
and verify the job definitions and permissions. This restores the
previous configuration where possible; it does not automatically reverse
data already written by a production job.

Any production table/schema migration therefore needs its own backup,
compatibility, and recovery plan. Prefer backward-compatible changes and
keep destructive data operations out of the deployment workflow.

## 7. Readiness checklist

### Required before production Databricks deployment

-   [ ] Protect `main` and require pull requests and successful checks.
-   [ ] Verify AWS OIDC trust conditions and least-privilege SSM
    permissions.
-   [ ] Separate the AWS SSM test role from the deployment role, or
    retire the test workflow.
-   [ ] Pin GitHub Actions to verified full commit SHAs.
-   [ ] Add concurrency protection to Databricks DEV deployment.
-   [ ] Verify the DEV Databricks service principal's actual grants.
-   [ ] Add a separate production Databricks service principal.
-   [ ] Add a non-default `prod` Asset Bundle target with a separate
    workspace root and production catalog.
-   [ ] Create the protected `databricks-production` GitHub Environment
    and configure required reviewers.
-   [ ] Create a manual-only production deployment workflow.
-   [ ] Test the production deployment and rollback process without
    running data-changing jobs.

### Additional control for the existing Dash EC2 deployment

-   [ ] Create a protected `ec2-production` GitHub Environment and add
    required reviewers to the Dash deployment job if manual approval is
    required for every live Dash release.

## 8. Current release policy

Until the checklist is completed:

-   DEV Databricks deployment may remain automatic from
    `feature/databricks-bundles`.
-   Databricks production deployment remains disabled and manual by
    design.
-   The existing Dash EC2 deployment behavior is unchanged by this
    review; it currently remains automatic after eligible successful
    Dash CI runs on `main`.
-   No production catalog, production data, or production credentials
    are changed by this documentation work.
