#!/usr/bin/python
# build_rf_model.py


from operator import itemgetter
#from rpy2.robjects.packages import importr
#from rpy2 import robjects
import shutil
import sklearn as skl
from sklearn.ensemble import RandomForestClassifier as RFC
from sklearn.externals import joblib
from sklearn.cross_validation import train_test_split
from sklearn.metrics import confusion_matrix
from random import shuffle
import cPickle
import lc_tools
import sys
import os
import cfg
import numpy as np
import datetime
import pytz
import tarfile
import glob
try:
    from disco.core import Job, result_iterator
    from disco.util import kvgroup
    DISCO_INSTALLED = True
except Exception as theError:
    DISCO_INSTALLED = False
if DISCO_INSTALLED:
    import parallel_processing
import custom_exceptions
sys.path.append(cfg.TCP_INGEST_TOOLS_PATH)
# for when run from inside docker container:
sys.path.append("/home/mltsp/TCP/Software/ingest_tools")
import generate_science_features
import custom_feature_tools as cft


def read_data_from_csv_file(fname,sep=',',skip_lines=0):
    """Parse CSV file and return data in list form.
    
    Parameters
    ----------
    fname : str
        Path to the CSV file.
    sep : str, optional
        Delimiting character in CSV file. Defaults to ",".
    skip_lines : int, optional
        Number of leading lines to skip in file. Defaults to 0.
    
    Returns
    -------
    list of list
        Two-element list whose first element is a list of the column 
        names in the file, and whose second element is a list of lists, 
        each list containing the values in each row in the file.
    
    """
    f = open(fname)
    linecount = 0
    data_rows = []
    all_rows = []
    for line in f:
        if linecount >= skip_lines:
            if linecount == 0:
                colnames = line.strip('\n').split(sep)
                all_rows.append(colnames)
            else:
                data_rows.append(line.strip('\n').split(sep))
                all_rows.append(line.strip('\n').split(sep))
                if "?" in line:
                    # Replace missing values with 0.0
                    data_rows[-1] = [el if el != "?" else "0.0" 
                                     for el in data_rows[-1]]
                    all_rows[-1] = [el if el != "?" else "0.0" 
                                    for el in all_rows[-1]]
        linecount+=1
    for i in range(len(colnames)):
        colnames[i] = colnames[i].strip('"')
    print linecount-1, "lines of data successfully read."
    f.close()
    #return all_rows
    return [colnames,data_rows]


def build_model(
    featureset_name, featureset_key, model_type="RF", 
    in_docker_container=False):
    """Build a `scikit-learn` classifier.
    
    Builds the specified model and pickles it in the file 
    whose name is given by 
    ``"%s_%s.pkl" % (featureset_key, model_type)``
    in the directory `cfg.MODELS_FOLDER` (or is later copied there 
    from within the Docker container if `in_docker_container` is True.
    
    Parameters
    ----------
    featureset_name : str
        Name of the feature set to build the model upon (will also 
        become the model name).
    featureset_key: str
        RethinkDB ID of the associated feature set from which to build 
        the model, which will also become the ID/key for the model.
    model_type : str
        Abbreviation of the type of classifier to be created. Defaults 
        to "RF".
    in_docker_container : bool, optional
        Boolean indicating whether function is being called from within 
        a Docker container.
    
    Returns
    -------
    str
        Human-readable message indicating successful completion.
    
    """
    if in_docker_container:
        features_folder = "/Data/features/"
        models_folder = "/Data/models/"
        uploads_folder = "/Data/flask_uploads/"
    else:
        features_folder = cfg.FEATURES_FOLDER
        models_folder = cfg.MODELS_FOLDER
        uploads_folder = cfg.UPLOAD_FOLDER
    
    all_features_list = cfg.features_list[:] + cfg.features_list_science[:]
    features_to_use = all_features_list
    features_filename = os.path.join(
        features_folder, "%s_features.csv" % featureset_key)
    
    features_extracted, all_data = read_data_from_csv_file(features_filename)
    classes = joblib.load(
        features_filename.replace("_features.csv","_classes.pkl"))
    data_dict = {}
    data_dict['features'] = all_data
    data_dict['classes'] = classes
    del all_data
    
    class_count = {}
    numobjs = 0
    class_list = []
    cv_objs = []
    # count up total num of objects per class
    print "Starting class count..."
    for classname in classes:
        if classname not in class_list:
            class_list.append(classname)
            class_count[classname] = 1
        else:
            class_count[classname] += 1
    print "Done."
    print "class_count:", class_count

    sorted_class_list = sorted(class_list)
    del classes
    
    ## remove any empty lines from data:
    print "\n\n"
    line_lens = []
    indices_for_deletion = []
    line_no = 0
    print type(data_dict['features']), len(data_dict['features'])
    for i in range(len(data_dict['features'])):
        line = data_dict['features'][i]
        if len(line) not in line_lens:
            line_lens.append(len(line))
            if len(line) == 1:
                indices_for_deletion.append(i)
        line_no += 1
    print line_no, "total lines in features csv."
    print "line_lens:", line_lens
    print len(data_dict['features'])
    if len(indices_for_deletion) == 1:
        del data_dict['features'][indices_for_deletion[0]]
        del data_dict['classes'][indices_for_deletion[0]]
    print len(data_dict['features'])
    print "\n\n"
    
    ntrees = 1000
    njobs = -1
    
    #### build the model:
    # initialize:
    rf_fit = RFC(n_estimators=ntrees,max_features='auto',n_jobs=njobs)
    print "Model initialized."
    
    # fit the model:
    print "Fitting the model..."
    rf_fit.fit(data_dict['features'],data_dict['classes'])
    print "Done."
    del data_dict
    
    # store the model:
    print "Pickling model..."
    foutname = os.path.join(
        ("/tmp" if in_docker_container else models_folder), 
        "%s_%s.pkl" % (featureset_key,model_type))
    joblib.dump(rf_fit,foutname,compress=3)
    print foutname, "created."
    
    if 0: # cross validation
        ############# CROSS-VALIDATION ##################
        cv_results_dict = {}
        for class_name in class_list:
            cv_results_dict[class_name] = {'correct': 0, 'incorrect': 0}
        for obj in cv_objs:
            try:
                newFeatures = []
                for feat in cfg.features_list:
                    if feat in features_to_use and feat in features_extracted:
                        newFeatures.append(obj[feat])
                
                classifier_preds = rf_fit.predict_proba(newFeatures)
                class_probs = classifier_preds[0]
            except ValueError as the_error:
                print the_error
                continue
            results_arr = []
            
            for i in range(len(class_probs)):
                results_arr.append(
                    [sorted_class_list[i],float(class_probs[i])])
            results_arr.sort(key=itemgetter(1),reverse=True)
            top_class = results_arr[0][0]
            print results_arr
            print obj['class']
            if top_class == obj['class']:
                cv_results_dict[obj['class']]['correct'] += 1
                print "Correct."
            else:
                cv_results_dict[obj['class']]['incorrect'] += 1
                print "Incorrect."
        print cv_results_dict

        for class_name in class_list:
            print class_name,"percent correct:",\
                float(cv_results_dict[class_name]['correct'])/float(
                    cv_results_dict[class_name]['correct']
                    +cv_results_dict[class_name]['incorrect'])
    del rf_fit
    print "DONE!"
    return ("New model successfully created. Click the Predict tab to "
        "start using it.")


def featurize(
    headerfile_path, zipfile_path, features_to_use=[], 
    featureset_id="unknown", is_test=False, USE_DISCO=True, 
    already_featurized=False, custom_script_path=None, 
    in_docker_container=False):
    """Generates features for labeled time series data.
    
    Features are saved to the file given by 
    ``"%s_features.csv" % featureset_id``
    and a list of corresponding classes is saved to the file given by 
    ``"%s_classes.pkl" % featureset_id``
    in the directory `cfg.FEATURES_FOLDER` (or is later copied there if 
    generated inside a Docker container).
    
    Parameters
    ----------
    headerfile_path : str
        Path to header file containing file names, class names, and 
        metadata.
    zipfile_path : str
        Path to the tarball of individual time series files to be used 
        for feature generation.
    features_to_use : list, optional
        List of feature names to be generated. Defaults to an empty 
        list, which results in all available features being used.
    featureset_id : str, optional
        RethinkDB ID of the new feature set entry. Defaults to 
        "unknown".
    is_test : bool, optional
        Boolean indicating whether to do a test run of only the first 
        five time-series files. Defaults to False.
    USE_DISCO : bool, optional
        Boolean indicating whether to featurize in parallel using Disco.
        Defaults to True.
    already_featurized : bool, optional
        Boolean indicating whether `headerfile_path` points to a file 
        containing pre-generated features, in which case `zipfile_path` 
        must be None. Defaults to False.
    custom_script_path : str, optional
        Path to Python script containing function definitions for the 
        generation of any custom features. Defaults to None.
    in_docker_container : bool, optional
        Boolean indicating whether function is being called from inside 
        a Docker container. Defaults to False.
    
    Returns
    -------
    str
        Human-readable message indicating successful completion.
    
    """
    if in_docker_container:
        features_folder = "/Data/features/"
        models_folder = "/Data/models/"
        uploads_folder = "/Data/flask_uploads/"
    else:
        features_folder = cfg.FEATURES_FOLDER
        models_folder = cfg.MODELS_FOLDER
        uploads_folder = cfg.UPLOAD_FOLDER
    
    if "/" not in headerfile_path:
        headerfile_path = os.path.join(uploads_folder,headerfile_path)
    if zipfile_path is not None and "/" not in zipfile_path:
        zipfile_path = os.path.join(uploads_folder,zipfile_path)
    all_features_list = cfg.features_list[:] + cfg.features_list_science[:]
    if already_featurized:
        objects = []
        with open(headerfile_path) as f:
            keys = f.readline().strip().split(',')
            for line in f:
                vals = line.strip().split(",")
                if len(vals)!=len(keys):
                    continue
                else:
                    objects.append({})
                    for i in range(len(keys)):
                        objects[-1][keys[i]] = vals[i]
    else: # EXTRACT FEATURES::
        if len(features_to_use) == 0:
            features_to_use = all_features_list
        with open(headerfile_path,'r') as headerfile:
            fname_class_dict = {}
            fname_class_science_features_dict = {}
            fname_metadata_dict = {}
            objects = []
            # write ids and classnames to dict
            line_no = 0
            other_metadata_labels = []
            for line in headerfile:
                if line_no == 0:
                    els = line.strip().split(',')
                    fname, class_name = els[:2]
                    other_metadata_labels = els[2:]
                    features_to_use += other_metadata_labels
                else:
                    if len(line) > 1 and line[0] not in ["#","\n"]:
                        if len(line.split(',')) == 2:
                            fname,class_name = line.strip('\n').split(',')
                            fname_class_dict[fname] = class_name
                            fname_class_science_features_dict[fname] = {
                                'class':class_name}
                        elif len(line.split(',')) > 2:
                            els = line.strip().split(',')
                            fname, class_name = els[:2]
                            other_metadata = els[2:]
                            # convert to floats, if applicable:
                            for i in range(len(other_metadata)):
                                try:
                                    other_metadata[i] = float(
                                        other_metadata[i])
                                except ValueError:
                                    pass
                            fname_class_dict[fname] = class_name
                            fname_class_science_features_dict[fname] = {
                                'class':class_name}
                            
                            fname_metadata_dict[fname] = dict(
                                zip(other_metadata_labels, other_metadata))
                line_no += 1
        # disco may be installed in docker container, but 
        # it is not working yet, thus the " and not in_docker_container"
        if DISCO_INSTALLED and USE_DISCO:# and not in_docker_container:
            print "FEATURIZE - USING DISCO"
            fname_features_data_dict = (
                parallel_processing.featurize_in_parallel(
                    headerfile_path=headerfile_path, zipfile_path=zipfile_path,
                    features_to_use=features_to_use, is_test=is_test, 
                    custom_script_path=custom_script_path, 
                    meta_features=fname_metadata_dict))
            for k,v in fname_features_data_dict.iteritems():
                if k in fname_metadata_dict:
                    v = dict(v.items() + fname_metadata_dict[k].items())
                objects.append(v)
        else:
            print "FEATURIZE - NOT USING DISCO"
            zipfile = tarfile.open(zipfile_path)
            zipfile.extractall(path=os.path.join(uploads_folder,"unzipped"))
            all_fnames = zipfile.getnames()
            num_objs = len(fname_class_dict)
            zipfile_name = zipfile_path.split("/")[-1]
            count=0
            print "Generating science features..."
            for fname in sorted(all_fnames):
                short_fname = (
                    fname.split("/")[-1]
                    .replace((
                        "."+fname.split(".")[-1] if "." in 
                        fname.split("/")[-1] else ""),""))
                path_to_csv = os.path.join(
                    uploads_folder, os.path.join("unzipped",fname))
                if os.path.isfile(path_to_csv):
                    print "Extracting features for", fname,"-", count, \
                        "of", num_objs
                    print "path_to_csv =", path_to_csv
                    ## generate features:
                    if len(set(features_to_use) & set(cfg.features_list)) > 0:
                        timeseries_features = (
                            lc_tools.generate_timeseries_features(
                                path_to_csv, 
                                classname=fname_class_dict[short_fname],
                                sep=','))
                    else:
                        timeseries_features = {}
                    if len(
                            set(features_to_use) & 
                            set(cfg.features_list_science)) > 0:
                        science_features = generate_science_features.generate(
                            path_to_csv=path_to_csv)
                    else:
                        science_features = {}
                    if custom_script_path not in (None, "None", 
                                                  False, "False"):
                        custom_features = cft.generate_custom_features(
                            custom_script_path=custom_script_path,
                            path_to_csv=path_to_csv,
                            features_already_known=dict(
                                list(timeseries_features.items()) + 
                                list(science_features.items())))
                        if (type(custom_features) == list and 
                            len(custom_features) == 1):
                                custom_features = custom_features[0]
                    else:
                        custom_features = {}
                    all_features = dict(
                        timeseries_features.items() + 
                        science_features.items() + 
                        custom_features.items())
                    if short_fname in fname_metadata_dict:
                        all_features = dict(
                            all_features.items() + 
                            fname_metadata_dict[short_fname].items())
                    fname_class_science_features_dict[
                        short_fname]['features'] = all_features
                    
                    objects.append(
                        fname_class_science_features_dict[
                            short_fname]['features'])
                    objects[-1]['class'] = fname_class_dict[short_fname]
                    count += 1
                    if is_test and count > 2:
                        break
                else:
                    pass
            print "Done."
        try:
            all_fnames
        except:
            zipfile = tarfile.open(zipfile_path)
            all_fnames = zipfile.getnames()
        finally:
            for fname in all_fnames:
                path_to_csv = os.path.join(
                    uploads_folder, os.path.join("unzipped",fname))
                if os.path.isfile(path_to_csv):
                    os.remove(path_to_csv)
    features_extracted = objects[-1].keys()
    if "class" in features_extracted:
        features_extracted.remove("class")
    if len(set(cfg.features_to_plot) & set(features_extracted)) < 2:
        features_extracted_copy = features_extracted[:]
        shuffle(features_extracted_copy)
        features_to_plot = features_extracted_copy[:5]
    else:
        features_to_plot = cfg.features_to_plot
    foutname = os.path.join(features_folder, "%s.pkl" % featureset_id)
    f = open(os.path.join(
        ("/tmp" if in_docker_container else features_folder),
         "%s_features.csv" % featureset_id),'w')
    f2 = open(os.path.join(
        ("/tmp" if in_docker_container else features_folder),
         "%s_features_with_classes.csv" % featureset_id),'w')
    line = []
    line2 = ['class']
    for feat in sorted(features_extracted):
        if feat in features_to_use:
            print "Using feature", feat
            line.append(feat)
            if feat in features_to_plot:
                line2.append(feat)
    f.write(','.join(line) + '\n')
    #line2.extend(line)
    f2.write(','.join(line2)+'\n')
    
    classes = []
    class_count = {}
    numobjs = 0
    num_used = {}
    num_held_back = {}
    class_list = []
    cv_objs = []
    # count up total num of objects per class
    print "Starting class count..."
    shuffle(objects) 
    for obj in objects:
        if str(obj['class']) not in class_list:
            class_list.append(str(obj['class']))
            class_count[str(obj['class'])] = 1
            num_used[str(obj['class'])] = 0
            num_held_back[str(obj['class'])] = 0
        else:
            class_count[str(obj['class'])] += 1
    print "Done."
    print "class_count:", class_count
    sorted_class_list = sorted(class_list)
    print "Writing object features to file..."
    for obj in objects:
        # total number of lcs for given class encountered < 70% total num lcs
        #if (num_used[str(obj['class'])] + num_held_back[str(obj['class'])] 
        #   < 0.7*class_count[str(obj['class'])]):
        
        # overriding above line that held back 30% of objects from model 
        # creation for CV purposes :
        if 1:
            line = []
            line2 = [obj['class']]
            for feat in sorted(features_extracted):
                if feat in features_to_use:
                    try:
                        if type(obj[feat]) == str and obj[feat] != "None":
                            line.append(obj[feat])
                        elif (type(obj[feat]) == type(None) 
                              or obj[feat] == "None"):
                            line.append(str(0.0))
                        else:
                            line.append(str(obj[feat]))
                        if feat in features_to_plot and numobjs < 300:
                            if type(obj[feat]) == str and obj[feat] != "None":
                                line2.append(obj[feat])
                            elif (type(obj[feat]) == type(None) 
                                  or obj[feat] == "None"):
                                line2.append(str(0.0))
                            else:
                                line2.append(str(obj[feat]))
                    except KeyError:
                        print feat, "NOT IN DICT KEYS!!!! SKIPPING..."
            f.write(','.join(line) + '\n')
            if numobjs < 300:
                f2.write(','.join(line2) + '\n')
            classes.append(str(obj['class']))
            num_used[str(obj['class'])] += 1
        else:
            cv_objs.append(obj)
            num_held_back[str(obj['class'])] += 1
        numobjs += 1
    f.close()
    f2.close()
    if not in_docker_container:
        shutil.copy2(
            f2.name,os.path.join(cfg.PROJECT_PATH,"flask/static/data"))
    print "Done."
    del objects
    if not in_docker_container:
        os.remove(os.path.join(
            features_folder, "%s_features_with_classes.csv" % featureset_id))
    joblib.dump(classes,os.path.join(
        ("/tmp" if in_docker_container else features_folder),
        "%s_classes.pkl" % featureset_id),compress=3)
    print foutname.replace(".pkl","_features.csv"), "and", \
        foutname.replace(".pkl","_features_with_classes.csv"), "and", \
        foutname.replace(".pkl","_classes.pkl"), "created."
    os.remove(headerfile_path)
    if zipfile_path is not None:
        os.remove(zipfile_path)
    print (str(foutname.replace(".pkl","_features.csv").split('/')[-1] + 
        " and " + foutname.replace(".pkl","_classes.pkl").split('/')[-1] + 
        " created."))
    return "Featurization of timeseries data complete."


if __name__ == "__main__":
    if len(sys.argv) == 2:
        features_to_use = list(sys.argv[1])
    else:
        features_to_use = []
    build_model(features_to_use=features_to_use)
    

