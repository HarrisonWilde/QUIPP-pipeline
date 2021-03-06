"""
Code to calculate utility metrics based on
the training & prediction of ML classifiers.
"""

import codecs
import importlib
import json
import os
import random
import sys
import warnings
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer

sys.path.append(os.path.join(os.path.dirname(__file__), os.path.pardir, "utilities"))
sys.path.append(os.path.join(os.path.dirname(__file__), os.path.pardir, "report"))
from utils import handle_cmdline_args, extract_parameters, find_column_types
import report


# classifiers
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import RBF
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, AdaBoostClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import confusion_matrix


def classifier_metrics(synth_method, path_original_ds,
                       path_original_meta, path_released_ds,
                       input_columns, label_column,
                       test_train_ratio, classifiers,
                       num_leaked_rows=0, random_seed=1234,
                       disable_all_warnings=True,
                       verbose=False):
    """
    Calculates ML classifier performance metrics for the original
    and released datasets, which are then compared to estimate the
    utility of the released dataset. Results are saved to .json files
    and an html report is generated.

    Parameters
    ----------
    synth_method : string
        The synthesis method used to create the released dataset.
    path_original_ds : string
        Path to the original dataset.
    path_original_meta : string
        Path to the original metadata.
    path_released_ds : string
        Path to the released dataset.
    input_columns : list
        List of names of feature columns (independent variables)
        that will be used for classification in all classifiers.
    label_column : sting
        Name of label column (dependent/predicted variable) that
        will be used for classification in all classifiers.
    test_train_ratio : float
        Test-train ratio to be used for classification.
    classifiers : dict
        Dictionary containing classifiers to be used (keys) and
        tuning parameters for each (values). The tuning parameters
        of each classifier should be wihtin a dictionary.
    num_leaked_rows: integer
        Number of rows to copy from original to released dataset.
        This can be used to artificially simulate a situation where
        the synthesis method does not demonstrate good privacy and
        thus leads to release or rows from the original into the
        synthetic dataset. Defaults to 0.
    random_seed : integer
        Random seed for numpy and ML algorithm. Defaults to 1234.
    disable_all_warnings : bool
        Disable all warning messages.
    verbose : bool
        If True, print all info messages.
    """

    print("[INFO] Calculating classifier-based utility metrics")

    # set random seeds
    random.seed(random_seed)
    np.random.seed(random_seed)
    np.random.default_rng(random_seed)

    if disable_all_warnings:
        if not sys.warnoptions:
            warnings.simplefilter("ignore")
            os.environ["PYTHONWARNINGS"] = "ignore"  # also affect subprocesses

    # read metadata in JSON format
    with open(path_original_meta) as orig_metadata_json:
        orig_metadata = json.load(orig_metadata_json)

    # divide columns into discrete and numeric,
    # discrete columns will be later vectorized
    discrete_types = ['Categorical', 'Ordinal', 'DiscreteNumerical', 'DateTime']
    discrete_features, numeric_features = \
        find_column_types(orig_metadata, synth_method, discrete_types)

    # read original and released/synthetic datasets
    # only the first synthetic data set is used for utility evaluation
    orig_df = pd.read_csv(path_original_ds)
    rlsd_df = pd.read_csv(path_released_ds + "/synthetic_data_1.csv")

    # fill all NaNs in datasets
    orig_df.fillna(orig_df.median(), inplace=True)
    rlsd_df.fillna(rlsd_df.median(), inplace=True)

    # introduce leaked rows
    if num_leaked_rows > 0:
        rlsd_df[:num_leaked_rows] = orig_df[:num_leaked_rows]

    # split original into X/y and train/test
    X_o, y_o = orig_df[input_columns], orig_df[label_column]
    X_train_o, X_test_o, y_train_o, y_test_o = \
        train_test_split(X_o, y_o, test_size=test_train_ratio,
                         random_state=random_seed)

    # split released into X/y and train/test
    X_r, y_r = rlsd_df[input_columns], rlsd_df[label_column]
    X_train_r, X_test_r, y_train_r, y_test_r = \
        train_test_split(X_r, y_r, test_size=test_train_ratio,
                         random_state=random_seed)

    # create preprocessing pipelines for both numeric and discrete data.
    # SimpleImputer: Imputation transformer for completing missing values.
    # StandardScaler: Standardize features by removing the
    # mean and scaling to unit variance
    # OneHotEncoder: Encode discrete features as a one-hot numeric array.
    numeric_transformer = Pipeline(steps=[('scaler', StandardScaler())])
    discrete_transformer = \
        Pipeline(steps=[('onehot', OneHotEncoder(sparse=False,
                                                 handle_unknown='ignore'))])

    # extract numeric/discrete features contained in input columns
    numeric_features_in_df = list(set(numeric_features).intersection(input_columns))
    discrete_features_in_df = list(set(discrete_features).intersection(input_columns))

    # column transformer
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features_in_df),
            ('cat', discrete_transformer, discrete_features_in_df)
        ])

    # train and score each classifier for both datasets,
    # using different metrics (accuracy, precision, recall, F1)
    # two values are calculated for each metric
    #   * trained on original, tested on original
    #   * trained on released, tested on original
    utility_o_o = {}
    utility_r_o = {}
    utility_diff = {}
    utility_confusion_o_o = {}
    utility_confusion_r_o = {}
    for one_clf in classifiers:

        clf_name = one_clf.__name__

        with warnings.catch_warnings(record=True) as warns:

            # original dataset
            # append classifier to preprocessing pipeline.
            if classifiers[one_clf]["mode"] == "main":
                parameters = classifiers[one_clf]["params_main"]
                clf_orig = Pipeline(steps=[('preprocessor', preprocessor),
                                           ('classifier', one_clf(**parameters))])
            else:
                parameters = classifiers[one_clf]["params_range"]
                clf_orig = Pipeline(steps=[('preprocessor', preprocessor),
                                           ('classifier', one_clf())])
                clf_orig = GridSearchCV(clf_orig, parameters,
                                        scoring="f1_macro", n_jobs=-1)
            # train classifier on original training set
            # and predict original testing set
            clf_orig.fit(X_train_o, y_train_o)
            y_test_pred_o_o = clf_orig.predict(X_test_o)

            # released dataset
            # append classifier to preprocessing pipeline.
            if classifiers[one_clf]["mode"] == "main":
                clf_rlsd = Pipeline(steps=[('preprocessor', preprocessor),
                                           ('classifier', one_clf(**parameters))])
            else:
                parameters_rlsd = {k.split("classifier__")[1]: v for k, v
                                   in clf_orig.best_params_.items()}
                clf_rlsd = Pipeline(steps=[('preprocessor', preprocessor),
                                           ('classifier', one_clf(**parameters_rlsd))])
            # train classifier on released training set
            # and predict original testing set
            clf_rlsd.fit(X_train_r, y_train_r)
            y_test_pred_r_o = clf_rlsd.predict(X_test_o)

            # calculate and store all metrics for both train/test combinations
            utility_o_o[clf_name] = calculate_metrics(y_test_pred_o_o, y_test_o)
            utility_r_o[clf_name] = calculate_metrics(y_test_pred_r_o, y_test_o)

            # calculate and store metrics' relative differences between
            # original/original and released/original settings
            utility_diff[clf_name] = calculate_diff_metrics(utility_o_o[clf_name], utility_r_o[clf_name])

            # calculate and store confusion matrices
            utility_confusion_o_o[clf_name] = calculate_confusion_matrix(y_test_pred_o_o,
                                                                         y_test_o,
                                                                         target_names=clf_orig.classes_)
            utility_confusion_r_o[clf_name] = calculate_confusion_matrix(y_test_pred_r_o,
                                                                         y_test_o,
                                                                         target_names=clf_rlsd.classes_)
    
    # mean relative differences for each metric (from all classifiers combined)
    utility_overall_diff = calculate_overall_diff(utility_diff)

    if verbose:
        print_metric(utility_o_o, title="Trained on original and tested on original")
        print_metric(utility_r_o, title="Trained on released and tested on original")
        print_metric(utility_overall_diff, title="Overall difference")

    # save output metrics to .json files
    save_json(utility_overall_diff, filename="utility_overall_diff.json", par_dir=path_released_ds)
    save_json(utility_diff, filename="utility_diff.json", par_dir=path_released_ds)
    save_json(utility_o_o, filename="utility_o_o.json", par_dir=path_released_ds)
    save_json(utility_r_o, filename="utility_r_o.json", par_dir=path_released_ds)
    save_json(utility_confusion_o_o, filename="utility_confusion_o_o.json", par_dir=path_released_ds)
    save_json(utility_confusion_r_o, filename="utility_confusion_r_o.json", par_dir=path_released_ds)

    # print any warnings
    if len(warns) > 0:
        print("WARNINGS:")
        for iw in warns:
            print(iw.message)

    # create output report
    report.report(path_released_ds)


def calculate_confusion_matrix(y_pred, y_test, target_names):
    """Calculate confusion matrix and save to dictionary"""
    output = {"conf_matrix": confusion_matrix(y_pred, y_test).tolist(),
              "target_names": target_names.tolist()}
    return output


def save_json(inp_dict, filename, par_dir):
    """Saves dictionary tp .json file after creating a
    directory par_dir if it does not exist already."""
    if not os.path.isdir(par_dir):
        os.makedirs(par_dir)
    path2save = os.path.join(par_dir, filename)
    with codecs.open(path2save, "w", encoding="utf-8") as write_file:
        json.dump(inp_dict, write_file)


def print_metric(inp_dict, title=" ", verbose=True):
    """Prints metrics from dictionary"""
    msg = ""
    msg += f"\n\n{title}" + "<br />"
    if verbose:
        print(f"\n\n{title}")
    for k_method, v_method in inp_dict.items():
        msg += "<br />"
        msg += f"{k_method}" + "<br />"
        msg += "-"*len(k_method) + "<br />"
        if verbose:
            print("")
            print(f"{k_method}")
            print("-"*len(k_method))
        for k_metric, v_metric in v_method.items():
            for k_value, v_value in v_metric.items():
                msg += f"{k_metric} ({k_value}): {v_value:.2f}" + "<br />"
                if verbose:
                    print(f"{k_metric} ({k_value}): {v_value}")
    return msg


def print_summary(inp_dict, title="Summary"):
    """Prints summary metrics from dictionary"""
    print()
    print(10*"*****")
    print(f"{title}")
    print("-"*len(title))
    for k_metric, v_metric in inp_dict.items():
        for k_value, v_value in v_metric.items():
            print(f"{k_metric} ({k_value}): {v_value}")


def calculate_overall_diff(util_diff):
    """Calculate mean difference across models"""
    list_methods = list(util_diff.keys())
    overall_diff_dict = {}
    overall_diff_dict["overall"] = {}
    for metric_k, metric_v in util_diff[list_methods[0]].items():
        overall_diff_dict["overall"][metric_k] = {}
        for avg_k, avg_v in metric_v.items():
            overall_diff_dict["overall"][metric_k][avg_k] = {}
            sum_avg = 0
            for one_method in list_methods:
                sum_avg += util_diff[one_method][metric_k][avg_k]
            overall_diff_dict["overall"][metric_k][avg_k] = sum_avg / len(list_methods)
    return overall_diff_dict


def calculate_diff_metrics(util1, util2):
    """Calculate relative difference between two utilities"""
    util_diff = {}
    for metric_k1, metric_v1 in util1.items():
        if metric_k1 not in util2:
            continue
        util_diff[metric_k1] = {}
        for avg_k1, avg_v1 in metric_v1.items():
            if avg_k1 not in util2[metric_k1]:
                continue
            diff = abs(avg_v1 - util2[metric_k1][avg_k1]) / max(1e-9, avg_v1)
            util_diff[metric_k1][avg_k1] = diff
    return util_diff


def calculate_metrics(y_pred, y_test,
                      metrics=None):
    """Computes metrics using a list of predictions
    and their ground-truth labels"""
    if metrics is None:
        metrics = [("accuracy", "value"),
                   ("precision", "macro"),
                   ("precision", "weighted"),
                   ("recall", "macro"),
                   ("recall", "weighted"),
                   ("f1", "macro"),
                   ("f1", "weighted")]
    util_collect = {}
    for method_name, ave_method in metrics:

        if method_name not in util_collect:
            util_collect[method_name] = {}

        if method_name.lower() in ["precision"]:
            util_collect[method_name][ave_method] = \
                precision_score(y_pred, y_test, average=ave_method,
                                zero_division=True) * 100.
        elif method_name.lower() in ["recall"]:
            util_collect[method_name][ave_method] = \
                recall_score(y_pred, y_test, average=ave_method,
                             zero_division=True) * 100.
        elif method_name.lower() in ["f1", "f-1"]:
            util_collect[method_name][ave_method] = \
                f1_score(y_pred, y_test, average=ave_method,
                         zero_division=True) * 100.
        elif method_name.lower() in ["accuracy"]:
            util_collect[method_name][ave_method] = \
                accuracy_score(y_pred, y_test) * 100.

    return util_collect


def main():
    # process command line arguments
    args = handle_cmdline_args()

    # read run input parameters file
    with open(args.infile) as f:
        synth_params = json.load(f)

    # if the whole .json is not enabled or if the
    # classifiers utility metric is not enabled, stop here
    if not (synth_params["enabled"] and
            synth_params[f'utility_parameters_classifiers']['enabled']):
        return

    # extract paths and other parameters from args
    synth_method, path_original_ds, \
    path_original_meta, path_released_ds, \
    random_seed = extract_parameters(args, synth_params)

    # extract classification parameters from metadata json
    utility_parameters_classifiers = synth_params["utility_parameters_classifiers"]
    input_columns = utility_parameters_classifiers["input_columns"]
    label_column = utility_parameters_classifiers["label_column"]
    test_train_ratio = utility_parameters_classifiers["test_train_ratio"]
    num_leaked_rows = utility_parameters_classifiers["num_leaked_rows"]

    # create dictionary with classifier tuning parameters
    if "classifier" in utility_parameters_classifiers:
        classifiers_rd = synth_params["utility_parameters_classifiers"]["classifier"]
        classifiers = {}
        for c_keys in classifiers_rd.keys():
            classifiers[eval(c_keys)] = classifiers_rd[c_keys]
    else:
        print("[WARNING] 'classifier' could not be found, using default.")
        # list of classifiers and their arguments
        classifiers = {
            LogisticRegression:  {"mode": "range",
                                  "params_main": {"max_iter": 5000},
                                  "params_range": {"classifier__max_iter":
                                                   [10, 50, 100, 150, 180, 200, 250, 300]}
                                  },
            KNeighborsClassifier: {"mode": "main",
                                   "params_main": {"n_neighbors": 3},
                                   "params_range": {"classifier__n_neighbors": [3, 4, 5]}
                                   },
            SVC: {"mode": "range",
                  "params_main": {"kernel": "linear", "C": 0.025},
                  "params_range": {'classifier__C': [0.025, 0.05, 0.1, 0.5, 1],
                                   "classifier__kernel": ("linear", "rbf")}
                  },
            # GaussianProcessClassifier: {"mode": "main",
            #                            "params_main": {"kernel": 1.0 * RBF(1.0)},
            #                            "params_range": {}
            #                            },
            RandomForestClassifier: {"mode": "main", 
                                     "params_main": {"max_depth": 5,
                                                     "n_estimators": 10,
                                                     "max_features": 1,
                                                     "random_state": 123},
                                     "params_range": {}
                                     },
            # DecisionTreeClassifier: {"max_depth": 5},
            # MLPClassifier: {"alpha": 1, "max_iter": 5000},
            # AdaBoostClassifier: {},
            # GaussianNB: {},
            # QuadraticDiscriminantAnalysis: {}
        }

    # calculate and save classifier-based metrics
    classifier_metrics(synth_method, path_original_ds,
                       path_original_meta, path_released_ds,
                       input_columns, label_column,
                       test_train_ratio, classifiers,
                       num_leaked_rows, random_seed)


if __name__ == '__main__':
    main()
