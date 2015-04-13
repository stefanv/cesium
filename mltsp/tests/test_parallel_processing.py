from mltsp import parallel_processing as prl_proc
from mltsp import cfg
import numpy.testing as npt
import os
from os.path import join as pjoin
import pandas as pd
import shutil


DATA_PATH = pjoin(os.path.dirname(__file__), "data")


def test_featurize_in_parallel():
    """Test main parallelized featurization function"""
    fname_features_dict = prl_proc.featurize_in_parallel(
        pjoin(DATA_PATH,
              "asas_training_subset_classes.dat"),
        pjoin(DATA_PATH,
              "asas_training_subset.tar.gz"),
        features_to_use=["std_err", "freq1_harmonics_freq_0"],
        is_test=True, custom_script_path=None)
    assert isinstance(fname_features_dict, dict)
    for k, v in fname_features_dict.items():
        assert "std_err" in v and "freq1_harmonics_freq_0" in v


def test_featurize_prediction_data_in_parallel():
    """Test parallel featurization of prediction TS data"""
    shutil.copy(pjoin(DATA_PATH, "TESTRUN_features.csv"),
                cfg.FEATURES_FOLDER)
    shutil.copy(pjoin(DATA_PATH, "TESTRUN_classes.pkl"),
                cfg.FEATURES_FOLDER)
    shutil.copy(pjoin(DATA_PATH, "TESTRUN_RF.pkl"),
                cfg.MODELS_FOLDER)
    shutil.copy(pjoin(DATA_PATH, "215153_215176_218272_218934.tar.gz"),
                cfg.UPLOAD_FOLDER)
    shutil.copy(pjoin(DATA_PATH, "testfeature1.py"),
                pjoin(cfg.CUSTOM_FEATURE_SCRIPT_FOLDER,
                      "TESTRUN_CF.py"))

    features_and_tsdata_dict = prl_proc.featurize_prediction_data_in_parallel(
        pjoin(DATA_PATH, "215153_215176_218272_218934.tar.gz"),
        "TESTRUN")

    assert "std_err" in features_and_tsdata_dict\
        ["dotastro_218934.dat"]["features_dict"]
    os.remove(pjoin(cfg.UPLOAD_FOLDER,
                    "215153_215176_218272_218934.tar.gz"))
    os.remove(pjoin(cfg.FEATURES_FOLDER, "TESTRUN_features.csv"))
    os.remove(pjoin(cfg.FEATURES_FOLDER, "TESTRUN_classes.pkl"))
    os.remove(pjoin(cfg.MODELS_FOLDER, "TESTRUN_RF.pkl"))
    os.remove(pjoin(cfg.CUSTOM_FEATURE_SCRIPT_FOLDER, "TESTRUN_CF.py"))
