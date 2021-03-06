# docker_featurize.py

# to be run from INSIDE a docker container


import subprocess
import sys,os
sys.path.append("/home/mltp")
import custom_feature_tools as cft
import build_rf_model
import predict_class


from subprocess import Popen, PIPE, call
import cPickle

def predict():
    # load pickled ts_data and known features
    with open("/home/mltp/copied_data_files/function_args.pkl","rb") as f:
        function_args = cPickle.load(f)
    
    # ensure required files successfully copied into container:
    if "newpred_file_path" in function_args:
        newpred_file_path = str(function_args['newpred_file_path'])
        if os.path.isfile(newpred_file_path):
            pass
        else:
            raise Exception("ERROR - IN DOCKER CONTAINER predict - newpred_file_path = %s is not a file currently on disk."%newpred_file_path)
    else:
        raise Exception("ERROR - IN DOCKER CONTAINER predict - newpred_file_path not in function args.")
    
    if "custom_features_script" in function_args and function_args["custom_features_script"] not in [None,False,"None",""]:
        custom_features_script = str(function_args['custom_features_script'])
        if not os.path.isfile(custom_features_script):
            raise Exception("ERROR - (IN DOCKER CONTAINER) predict - custom_features_script = %s is not a file currently on disk."%custom_features_script)
    if "metadata_file" in function_args and function_args["metadata_file"] not in [None,False,"None",""]:
        metadata_file = str(function_args['metadata_file'])
        if not os.path.isfile(metadata_file):
            raise Exception("ERROR - (IN DOCKER CONTAINER) predict - metadata_file = %s is not a file currently on disk."%metadata_file)
    
    results_dict = predict_class.predict(function_args["newpred_file_path"], function_args["model_name"], function_args["model_type"], featset_key=function_args["featset_key"], sepr=function_args["sep"], n_cols_html_table=function_args["n_cols_html_table"], features_already_extracted=function_args["features_already_extracted"], custom_features_script=function_args["custom_features_script"], metadata_file_path=function_args["metadata_file"], in_docker_container=True)
    
    
    with open("/tmp/%s_pred_results.pkl"%function_args["prediction_entry_key"], "wb") as f:
        cPickle.dump(results_dict, f)
    
    print "Done."
    
    
    return "Featurization and prediction complete."









if __name__=="__main__":
    
    results_str = predict()
    print results_str
