from mltsp import build_model
from mltsp import featurize
from mltsp import predict_class
from mltsp import cfg
import numpy.testing as npt
import os
from os.path import join as pjoin
import pandas as pd
import shutil


DATA_PATH = pjoin(os.path.dirname(__file__), "data")


def test_setup():
    """Setup"""
    print("Copying data files")
    # copy data files to proper directory:
    shutil.copy(
        pjoin(DATA_PATH, "asas_training_subset_classes_with_metadata.dat"),
        cfg.UPLOAD_FOLDER)

    shutil.copy(
        pjoin(DATA_PATH, "asas_training_subset.tar.gz"),
        cfg.UPLOAD_FOLDER)

    shutil.copy(
        pjoin(DATA_PATH, "testfeature1.py"),
        cfg.CUSTOM_FEATURE_SCRIPT_FOLDER)


def test_featurize():
    """Test main featurize function."""
    results_msg = featurize.featurize(
        headerfile_path=pjoin(
            cfg.UPLOAD_FOLDER,
            "asas_training_subset_classes_with_metadata.dat"),
        zipfile_path=pjoin(cfg.UPLOAD_FOLDER,
                           "asas_training_subset.tar.gz"),
        features_to_use=["std_err"],# #TEMP# TCP still broken under py3
        featureset_id="TESTRUN", is_test=True,
        custom_script_path=pjoin(cfg.CUSTOM_FEATURE_SCRIPT_FOLDER,
                                 "testfeature1.py"),
        USE_DISCO=False)
    assert(os.path.exists(pjoin(cfg.FEATURES_FOLDER,
                                "TESTRUN_features.csv")))
    assert(not os.path.exists(pjoin(cfg.FEATURES_FOLDER,
                                    "TESTRUN_features_with_classes.csv")))
    assert(os.path.exists(pjoin(cfg.MLTSP_PACKAGE_PATH, "Flask/static/data",
                                "TESTRUN_features_with_classes.csv")))
    assert(os.path.exists(pjoin(cfg.FEATURES_FOLDER,
                                "TESTRUN_classes.pkl")))
    df = pd.io.parsers.read_csv(pjoin(cfg.FEATURES_FOLDER,
                                "TESTRUN_features.csv"))
    cols = df.columns
    values = df.values
    assert("std_err" in cols)


def test_build_model():
    """Test model build function."""
    results_msg = build_model.build_model(featureset_name="TESTRUN",
                                          featureset_key="TESTRUN")
    assert(os.path.exists(pjoin(cfg.MODELS_FOLDER, "TESTRUN_RF.pkl")))


def test_predict():
    """Test class prediction."""
    results_dict = predict_class.predict(
        pjoin(DATA_PATH, "dotastro_215153.dat"),
        "TESTRUN", "RF", "TESTRUN",
        custom_features_script=pjoin(cfg.CUSTOM_FEATURE_SCRIPT_FOLDER,
                                     "testfeature1.py"),
        metadata_file_path=pjoin(DATA_PATH, "215153_metadata.dat"))
    assert(isinstance(results_dict, dict))
    assert("dotastro_215153.dat" in results_dict)
    assert(isinstance(
        results_dict["dotastro_215153.dat"]["features_dict"]["std_err"], float))


def test_remove_created_files():
    """Remove files created by test suite."""
    for fname in [pjoin(cfg.FEATURES_FOLDER, "TESTRUN_features.csv"),
                  pjoin(cfg.FEATURES_FOLDER, "TESTRUN_classes.pkl"),
                  pjoin(cfg.MLTSP_PACKAGE_PATH, "Flask/static/data",
                        "TESTRUN_features_with_classes.csv"),
                  pjoin(cfg.CUSTOM_FEATURE_SCRIPT_FOLDER,
                        "testfeature1.py"),
                  pjoin(cfg.MODELS_FOLDER, "TESTRUN_RF.pkl")]:
        os.remove(fname)
