# Machine Learning and Model Evaluation

## Modeling Approach
The project has progressed from exploratory analysis to supervised model training and validation.

The model families being evaluated include:

* Logistic Regression.

* Decision Tree.

* Random Forest.

* HistGradientBoosting.

* XGBoost.

* LightGBM.

The experiments include baseline models and selected hyperparameter-optimized variants.

The workflow for the modeling is described below.

Since we wanted to check if the engineered features made a difference, the engineered features was compared to the original features

![image_1792759239529.png](./image_1792759239529.png "image_1792759239529.png")
<p align="center"><i>Fig 1: Overall workflow </i></p>

## Preprocessing Pipeline and Data Transformation

A reusable preprocessing pipeline was implemented using scikit-learn's `ColumnTransformer` and `Pipeline`. Numerical features were imputed using the median and standardized using `StandardScaler`, while the categorical `Type` feature was imputed and transformed using one-hot encoding.

The same preprocessing framework was used across all six classification models to maintain consistency during model comparison. Although scaling is particularly important for Logistic Regression, it was also applied to the tree-based models for a consistent workflow.

Preprocessing was fitted on the training data and subsequently applied to validation and test data using the learned transformations, preventing data leakage and ensuring consistent treatment of incoming records.

## Classification Metrics
For a binary classification like in the machine failure analysis, the following examples serves as a way to understand the classifcation metrics.

![Machine Condition Prediction Matrix.png](./Machine%20Condition%20Prediction%20Matrix.png "Machine Condition Prediction Matrix.png")
<p align="center"><i>Fig 2: Confusion Matrix </i></p>

What each outcome means in practice
- **True Positive (TP)**: The model correctly identifies a machine that fails. Maintenance can be arranged before or around the failure event, depending on the use case.
- **True Negative (TN)**: The model correctly identifies a healthy machine. No unnecessary failure alert is generated.
- **False Positive (FP)**: The model raises an alert for a machine that does not fail. This could lead to an unnecessary inspection or maintenance intervention.
- **False Negative**: The model predicts that a machine is healthy, but it actually fails. This is potentially costly because the failure goes undetected.

| Metric | Formula | Description |
| :--- | :--- | :--- |
| **Accuracy** | $$\frac{TP+TN}{Total}$$ | The share of all predictions that were correct. |
| **Precision** | $$\frac{TP}{TP+FP}$$ | How many predicted positives were actually positive (measures exactness). |
| **Recall (Sensitivity / True Positive Rate)** | $$\frac{TP}{TP+FN}$$ | How many actual positives the model managed to catch. |
| **Specificity (True Negative Rate)** | $$\frac{TN}{TN+FP}$$ | How many actual negatives the model correctly identified. |
| **F2-Score** | $$\frac{2\times \text{Precision}\times \text{Recall}}{\text{Precision}+\text{Recall}}$$ | The harmonic mean of precision and recall, useful for imbalanced data. |

For predictive maintenance, consider the trade-off:
- Prioritizing recall, catches more failing machines but may generate more false alarms.
- Priortizing precision generates more false alarms, but may  miss more failures.
- Prioritizing accuracy alone, the model may appear excellent simply because most machines do not fail.

To summarize, a false negative is a missed failure, while a false positive is an unnecessary alert. Which is worse depends on the equipment, the cost of downtime, and the cost of maintenance. In a critical industrial system, missing a failure could be much more expensive than inspecting a healthy machine. Therefore, in this project, recall is the main metric used.

## Modeling Results
### Phase 1: Baseline screening. Original Features and Engineered Features

![Validation Metric Comparison Scatterplots_1792768216048.png](./Validation%20Metric%20Comparison%20Scatterplots_1792768216048.png "Validation Metric Comparison Scatterplots_1792768216048.png")
<p align="center"><i>Fig 3: Original Features and engineered features baseline results </i></p>

This figure summarizes the baseline screening results for models trained on both the original features and the engineered features. To make the comparison easier to interpret, the models built on the original feature set are shown in shades of red, while the models built on the engineered feature set are shown in shades of blue.

Across the scatterplots, the engineered-feature models generally appear in the stronger region of the charts, with higher recall, higher F1, and more true positives, although in some cases this comes with trade-offs in false positives. The plots also make it easier to compare performance from multiple angles rather than relying on a single metric. Overall, the chart shows how the baseline screening process helped identify the most promising candidate models from both feature sets before moving to hyperparameter tuninig.

| Validation Metric | LightGBM — Engineered features | HistGradientBoosting — Engineered features | XGBoost — Engineered features |
| :--- | :--- | :--- | :--- |
| **Recall** | 83.33% | 81.48% | 79.63% |
| **Precision** | 91.84% | 89.80% | 86.00% |
| **F2 score** | 84.91% | 83.02% | 80.83% |
| **True positives** | 45 | 44 | 43 |
| **False negatives** | 9 | 10 | 11 |
| **False positives** | 4 | 5 | 7 |
| **Alert rate** | 3.06% | 3.06% | 3.13% |

Out of all the best 3 models (sorted by f2), LightGBM with engineered features is the strongest baseline candidate.It offers the best balance between detecting failures and limiting false alarms among the baseline models.

### Phase 2: Hyperparmeter tuning of  Baseline models.
![Validation Metric Comparison Dashboard.png](./Validation%20Metric%20Comparison%20Dashboard.png "Validation Metric Comparison Dashboard.png") 
<p align="center"><i>Fig 4: Hyperparmeter tuning of  Baseline models. </i></p>


Following baseline screening, Random Forest, Decision Tree, and Logistic Regression were dropped from further optimization, and the focus was narrowed to LightGBM, XGBoost, and HistGradientBoosting. Optuna was then used to tune the hyperparameters of the three remaining models using both original and engineered features.

The chart compares their validation F1 score, precision, recall, false negatives, false positives, and true positives. Original-feature models are shown in shades of red, while engineered-feature models are shown in shades of blue. These comparisons help assess the impact of feature engineering and hyperparameter optimization and identify the best trade-off between detecting machine failures and minimizing false alarms.



Although LightGBM achieved the highest F1 score, HistGradientBoosting achieved higher recall, detecting 47 of the 54 actual failures compared with 46 for LightGBM. This reduced the number of false negatives from eight to seven, but increased false positives from eight to 17.

Given the project's focus on predictive maintenance, where missing a potential machine failure may be more costly than generating an unnecessary maintenance alert, **HistGradientBoosting was selected as the preferred model**. This decision prioritizes failure detection over maximizing the F1 score, accepting a higher false-positive rate in exchange for fewer missed failures. The selected model will subsequently be evaluated on the held-out test set to assess its generalization performance.

Comparing the baseline to the tuned models
For all the model pairs, the optimized models beats the baseline models in terms of recall, but comes with a higher number of false positives 
- **LightGBM**: Optimization slightly improves F2 and recall, but doubles false positives from 4 to 8.
- **HistGradientBoosting**: Optimization produces the largest recall improvement, reducing missed failures from 10 to 7. However, false positives increase from 5 to 17.
- **XGBoost**: Optimization improves F2 and recall, but false positives increase from 7 to 16.

![Screenshot from 2026-10-23 11-45-41.png](./Screenshot%20from%202026-10-23%2011-45-41.png "Screenshot from 2026-10-23 11-45-41.png")

### Phase 3: Decision Threshold Optimization

#### What is a Threshold?
A decision threshold is the probability cutoff used to convert a model's predicted probability into a classification. For example, with a threshold of 0.5, a machine with a predicted failure probability of 70% is classified as a failure, while one with a probability of 30% is classified as healthy.

Rather than relying on the default threshold of 0.5, different thresholds were evaluated on the validation set to improve failure detection. Lowering the threshold generally increases recall by identifying more potential failures, but can also increase false alarms. Since missing a machine failure can be costly, threshold selection prioritized high recall while balancing precision and the F2 score. The selected threshold was recorded for each model alongside its validation metrics in MLflow.

#### How the Decision Threshold Was Selected

The decision threshold was selected by evaluating different probability cutoffs on the validation dataset. For each candidate threshold, the model's predicted probabilities were converted into binary failure predictions, and performance metrics—including recall, precision, F2 score, false positives, and false negatives—were calculated.

Given the importance of detecting machine failures, the proposed selection strategy is to identify thresholds that achieve at least 90% recall and then select the threshold with the highest precision, using F2 score as a tie-breaker. This approach prioritizes failure detection while limiting unnecessary maintenance alerts. The selected threshold is stored alongside the model to ensure consistent predictions during deployment.

![image_1792793106099.png](./image_1792793106099.png "image_1792793106099.png")
<p align="center"><i>Fig 5: Original Features Optimization using Threshold. </i></p>


![image_1792793408025.png](./image_1792793408025.png "image_1792793408025.png")
<p align="center"><i>Fig 6:Engineered Features Optimization using Threshold. </i></p>
