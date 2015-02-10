#!/usr/bin/env python 
"""

Contains Classes which wrap R classifiers using rpy2.

Tested using:
  R     2.11.1
  rpy2  2.1.9

"""
from __future__ import print_function
import os, sys
from rpy2.robjects.packages import importr
from rpy2 import robjects
#from numpy import array        # only tried out in missforest_parallel_*()
#import rpy2.robjects.numpy2ri  # only tried out in missforest_parallel_*()


def missforest_parallel_task(varInd, ximp, obsi, misi, varType, ntree, p):
    """ Task which is to be spawned off in Parallel onto IPython cluster
    and invoked from the activelearn_utils.py:parallelized_imputation()
    or activelearn_utils.py::IPython_Task_Administrator()

    This will do a task, atomized by (ntree, impute_feature_i, cross_valid_fold, cross_valid_case)
    """
    #import rpy2.robjects.numpy2ri # DEBUG ONLY!
    #import numpy # DEBUG ONLY!
    robjects.globalenv['varInd'] = robjects.IntVector(varInd)
    robjects.globalenv['ximp'] = ximp
    robjects.globalenv['obsi'] = robjects.BoolVector(obsi)
    robjects.globalenv['misi'] = robjects.BoolVector(misi)
    robjects.globalenv['varType'] = varType
    robjects.globalenv['ntree'] = ntree
    robjects.globalenv['p'] = p    
    robjects.r("""
obsY <- ximp[obsi, varInd] # training response
obsX <- ximp[obsi, seq(1, p)[-varInd]] # training variables
misX <- ximp[misi, seq(1, p)[-varInd]] # prediction variables
typeY <- varType[varInd]
blah <- 3
#ximp[misi, varInd] <- misY""")
    #import pdb; pdb.set_trace()
    #print
    #misY = array(robjects.r("misY"))
    #OOBerror_val = list(robjects.r("OOBerror_val"))[0]
    #return (misY, OOBerror_val)
    #return (0,0)
    #return {'obsY':array(robjects.r("obsY")),
    #        'obsY_20':robjects.r("obsY[20]"),
    #        'obsX_23':robjects.r("obsX[2,3]"),
    #        'obsX_1065':robjects.r("obsX[10,65]"),
    #        'ntree':robjects.r("ntree"),
    #        'typeY':robjects.r("typeY")}
    return {'ntree':robjects.r("blah")}


class Rpy2Classifier:
    """
    """
    def __init__(self, pars={},
                 algorithms_dirpath=''):
        # # # on citris33:  algorithms_dirpath='/global/home/users/dstarr/src/TCP/Algorithms'
        self.pars = pars

        ### NOTE: really only need to require() classifiers if we use them

        r_str = '''
    require(randomForest)
    require(party)
    set.seed(sample(1:10^5,1))
    source("%s/utils_classify.R")
    source("%s/missForest.R")
    ''' % (algorithms_dirpath, algorithms_dirpath)#, algorithms_dirpath)
        #source("%s/class_cv.R")
        
        #source("/home/pteluser/src/TCP/Algorithms/utils_classify.R")
        #NOTNEEDED#source("/home/pteluser/src/TCP/Algorithms/class_cv.R")
        robjects.r(r_str)


    def read_class_dat(self, fpath="/home/pteluser/scratch/features.dat"):
        """ Read Joey class.dat

        Taken from tutorial_rpy.py

        """
        lines = open(fpath).readlines()
        out_list = []
        for i, line in enumerate(lines):
            the_str = line.strip()
            if len(the_str) == 0:
                continue
            out_list.append(the_str)
        return out_list


    def read_features_dat(self, fpath="/home/pteluser/scratch/features.dat"):
        """ Read Joey features.dat
        
        Taken from tutorial_rpy.py

        """
        from rpy2 import robjects

        lines = open(fpath).readlines()
        out_list = []
        feat_val_dict = {}
        for i, line in enumerate(lines):
            if i == 0:
                feat_names_with_quotes = line.split()
                feat_names = []
                for feat_name in feat_names_with_quotes:
                    feat_names.append(feat_name.strip('"'))
                n_cols = len(feat_names)
                for fname in feat_names:
                    feat_val_dict[fname] = []
                continue # skip the header
            line_split = line.split()
            for i_f, feat_val in enumerate(line_split):
                if feat_val == 'NA':
                    out_list.append(None)
                    feat_val_dict[feat_names[i_f]].append(None)
                else:
                    out_list.append(float(feat_val))
                    feat_val_dict[feat_names[i_f]].append(float(feat_val))

        for feat_name, feat_list in feat_val_dict.items():
            feat_val_dict[feat_name] = robjects.FloatVector(feat_list)
            
        return {'feat_list':out_list,
                'n_cols':n_cols,
                'feat_names':feat_names,
                'feat_val_dict':feat_val_dict}


    def parse_joey_feature_class_datfile(self, feature_fpath='', class_fpath=''):
        """ Parse Joey's features.dat classes.dat.

        """
        f_dict = self.read_features_dat(fpath=feature_fpath)
        features = robjects.r['data.frame'](**f_dict['feat_val_dict'])

        class_list = self.read_class_dat(fpath=class_fpath)
        classes = robjects.StrVector(class_list)

        ### ??? Do this? :
        #robjects.globalenv['features'] = features
        #robjects.globalenv['classes'] = classes


        return {'features':features,
                'classes':classes}


    def parse_arff_header(self, arff_str='', ignore_attribs=[]):
        """ Parse a given ARFF string, replace @attribute with @ignored for attributes in
        ignore_attribs list (ala PARF data specification).

        Return arff header string.
        """
        lines = arff_str.split('\n')
        out_lines = []
        for line in lines:
            out_lines.append(line)
            if '@data' in line.lower():
                return out_lines
        return None # shouldn't get here.


    def parse_full_arff(self, arff_str='', parse_srcid=True, parse_class=True, 
                        skip_missingval_lines=False, fill_arff_rows=False):
        """ Parse class & features from a full arff file.
        """
        percent_list = []
        iters_list = []
        featname_list = []
        srcid_list = []
        class_list = []
        arff_rows = []
        #featval_long_list = []
        featname_longfeatval_dict = {}
        lines = arff_str.split('\n')
        for line in lines:
            if len(line) == 0:
                continue
            elif line[0] == '%':
                continue
            elif line[:10] == '@ATTRIBUTE':
                if (('class' in line) or
                    ('source_id' in line)):
                    #if line[11:16] == 
                    continue # I could store the potential classes somewhere
                else:
                    feat_name = line.split()[1]
                    featname_list.append(feat_name)
                    featname_longfeatval_dict[feat_name] = []
            elif line[0] == '@':
                #  -> could add to some feature structure
                continue
            elif (skip_missingval_lines and ('?' in line)):
                continue # we skip souirces/arrf lines which have missing values since R Randomforest (and maybe other classifiers) cannot handle missing values.
            else:
                ### Then we have a source row with features
                if parse_class:
                    #i_r = line.rfind("'")
                    #i_l = line.rfind("'", 0, i_r)
                    if '"' in line:
                        i_r = line.rfind('"')
                        i_l = line.rfind('"', 0, i_r)
                    else:
                        i_r = line.rfind("'")
                        i_l = line.rfind("'", 0, i_r)
                        
                    a_class = line[i_l+1:i_r]
                    class_list.append(a_class) #a_class.strip("'"))
                    shortline = line[:i_l -1] #feat_list[:-1]
                elems = shortline.split(',')
                if fill_arff_rows:
                    arff_rows.append(line)
                feat_list = elems
                if parse_srcid:
                    if elems[0].count('_') == 0:
                        src_id = elems[0]
                        srcid_list.append(src_id)
                    else:
                        tups = elems[0].split('_')
                        srcid = int(tups[0])
                        perc = float(tups[1])
                        niter = int(tups[2])
                        srcid_list.append(srcid)
                        percent_list.append(perc)
                        iters_list.append(niter)
                    feat_list = feat_list[1:]

                for i, elem in enumerate(feat_list):
                    feat_name = featname_list[i]
                    if elem == '?':
                        val = None
                    else:
                        try:
                            val = float(elem)
                        except:
                            val = elem
                    featname_longfeatval_dict[feat_name].append(val)

        #for feat_name, feat_longlist in featname_longfeatval_dict.items():
        #    featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        #features = robjects.r['data.frame'](**featname_longfeatval_dict)
        #classes = robjects.StrVector(class_list)
        #return {'features':features,
        #        'classes':classes,
        #        'class_list':class_list,
        #        'srcid_list':srcid_list,
        #        'percent_list':percent_list,
        #        'iters_list':iters_list}


        ### NOTE: We dont do this here anymore.  We do it closer to the R classifier building code:
        #for feat_name, feat_longlist in featname_longfeatval_dict.items():
        #    featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        #features = robjects.r['data.frame'](**featname_longfeatval_dict)
        #classes = robjects.StrVector(class_list)

        return {'featname_longfeatval_dict':featname_longfeatval_dict,
                'class_list':class_list,
                'srcid_list':srcid_list,
                'percent_list':percent_list,
                'iters_list':iters_list,
                'arff_rows':arff_rows}



    def insert_missing_value_features(self, arff_str='', noisify_attribs=[],
                                      prob_source_has_missing=0.2,
                                      prob_misattrib_is_missing=0.2):
        """ Insert some missing-value features to arff rows.
        Exepect the input to be a single string representation of arff with \n's.
        Returning a similar single string.
        """
        import random
        out_lines = []
        misattrib_name_to_id = {}
        i_attrib = 0
        lines = arff_str.split('\n')
        do_attrib_parse = True
        for line in lines:
            if do_attrib_parse:
                if line[:10] == '@ATTRIBUTE':
                    feat_name = line.split()[1]
                    if feat_name in noisify_attribs:
                        misattrib_name_to_id[feat_name] = i_attrib
                    i_attrib += 1
                elif '@data' in line.lower():
                    do_attrib_parse = False
                out_lines.append(line)
                continue
            ### Should only get here after hitting @data line, which means just feature lines
            if random.random() > prob_source_has_missing:
                out_lines.append(line)
                continue # don't set any attributes as missing for this source
            attribs = line.split(',')
            new_attribs = []
            for i, attrib_val in enumerate(attribs):
                if i in misattrib_name_to_id.values():
                    if random.random() <= prob_misattrib_is_missing:
                        new_attribs.append('?')
                        continue
                new_attribs.append(attrib_val)
            new_line = ','.join(new_attribs)
            out_lines.append(new_line)
        new_train_arff_str = '\n'.join(out_lines)
        return new_train_arff_str
    

    def train_randomforest(self, data_dict, do_ignore_NA_features=False,
                           ntrees=1000, mtry=25, nfolds=10, nodesize=5):
        """ Train a randomForest() R classifier

        Taken from class_cv.R : rf.cv (L40)
        """
        featname_longfeatval_dict = data_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in featname_longfeatval_dict.items():
            featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        data_dict['features'] = robjects.r['data.frame'](**featname_longfeatval_dict)
        data_dict['classes'] = robjects.StrVector(data_dict['class_list'])

        robjects.globalenv['x'] = data_dict['features']
        robjects.globalenv['y'] = data_dict['classes']
        
        if do_ignore_NA_features:
            feat_trim_str = 'x = as.data.frame(x[,-which(substr(names(x),1,4)=="sdss"   | substr(names(x),1,3)=="ws_")])'
        else:
            feat_trim_str = ''

        r_str = '''
        %s
    y = class.debos(y)

    ntrees=%d
    mtry=%d
    nfolds=%d
    rf_clfr = randomForest(x=x,y=y,mtry=mtry,ntree=ntrees,nodesize=%d)
        ''' % (feat_trim_str, ntrees, mtry, nfolds, nodesize)
        ### NOTE: when no classwt is given, this same prior is calculated, so no need to do it again:
        #n = length(y)
        #prior = table(y)/n
        #rf_clfr = randomForest(x=x,y=y,classwt=prior,mtry=mtry,ntree=ntrees,nodesize=%d)
        #
        #     rf_clfr = randomForest(x=x,y=y)

        classifier_out = robjects.r(r_str)
        #import pdb; pdb.set_trace()
        #print classifier_out
        return {'py_obj':classifier_out,
                'r_name':'rf_clfr'}


    # obsolete / backup:
    def actlearn_randomforest__nocost(self, traindata_dict={},
                              testdata_dict={},
                              do_ignore_NA_features=False,
                              ntrees=1000, mtry=25,
                              nfolds=10, nodesize=5,
                              num_srcs_for_users=100,
                              random_seed=0,
                              final_user_classifs={}):
        """ Train a randomForest() R classifier

        Taken from class_cv.R : rf.cv (L40)
        """
        if do_ignore_NA_features:
            print("actlearn_randomforest():: do_ignore_NA_features==True not implemented because obsolete")
            raise

        train_featname_longfeatval_dict = traindata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in train_featname_longfeatval_dict.items():
            train_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        traindata_dict['features'] = robjects.r['data.frame'](**train_featname_longfeatval_dict)
        traindata_dict['classes'] = robjects.StrVector(traindata_dict['class_list'])

        robjects.globalenv['xtr'] = traindata_dict['features']
        robjects.globalenv['ytr'] = traindata_dict['classes']
        
        test_featname_longfeatval_dict = testdata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in test_featname_longfeatval_dict.items():
            test_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        testdata_dict['features'] = robjects.r['data.frame'](**test_featname_longfeatval_dict)
        testdata_dict['classes'] = robjects.StrVector(testdata_dict['class_list'])

        robjects.globalenv['xte'] = testdata_dict['features']
        robjects.globalenv['yte'] = testdata_dict['classes']

        import pdb; pdb.set_trace()
        print()

        r_str  = '''

    m=%d

    ntrees=%d
    mtry=%d
    nfolds=%d

    ytr = class.debos(ytr)

    n.tr = length(ytr) # number of training data
    n.te = dim(xte)[1] # number of test data

    if(is.null(mtry)){ mtry = ceiling(sqrt(dim(xtr)[2]))} # set mtry
    rf_clfr = randomForest(x=xtr,y=ytr,xtest=xte,ntrees=ntrees,mtry=mtry,proximity=T,nodesize=%d)
    rho = rf_clfr$test$proximity # RF proximity matrix, n.tr by n.te matrix
        ''' % (num_srcs_for_users, ntrees, mtry, nfolds, nodesize)


        r_str += '''

    n.bar = apply(rho[1:n.te,(n.te+1):(n.te+n.tr)],1,sum) # avg. # training data in same terminal node
    p.hat = apply(rf_clfr$test$votes,1,max)
    err.decr = ((1-p.hat)/(n.bar+1)) %*%rho[1:n.te,1:n.te] # this is Delta V

    # choose probabalistically? or take top choices?
    if(FALSE){ # take top m choices
      select = which(err.decr >= sort(err.decr,decreasing=TRUE)[m])
    }else{ # sample from distribution defined by err.decr
      select = sample(1:n.te,m,prob=err.decr/sum(err.decr),replace=FALSE)}
        '''


        classifier_out = robjects.r(r_str)


        #robjects.globalenv['pred_forconfmat']
        #robjects.r("rf_clfr$classes")

        possible_classes = robjects.r("rf_clfr$classes")

        '''
        actlearn_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        #for i, srcid in enumerate(data_dict['srcid_list']):
        for i in robjects.globalenv['select']:
            # I think the robjects.globalenv['select'] R array has an index starting at i=1
            #   so this means if R array gives i=999, then this translates srcid_list[i=998]
            #   so this means if R array gives i=1, then this translates srcid_list[i=0]
            srcid = testdata_dict['srcid_list'][i-1]
            tups_list = zip(list(robjects.r("rf_clfr$test$votes[%d,]" % (i))),  possible_classes)
            tups_list.sort(reverse=True)
            for j in range(3):
                actlearn_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
        '''
        #import pdb; pdb.set_trace()
        #print

        actlearn_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        #for i, srcid in enumerate(data_dict['srcid_list']):

        for i in robjects.globalenv['select']:
            # I think the robjects.globalenv['select'] R array has an index starting at i=1
            #   so this means if R array gives i=999, then this translates srcid_list[i=998]
            #   so this means if R array gives i=1, then this translates srcid_list[i=0]
            srcid = testdata_dict['srcid_list'][i-1]# index is python so starts at 0
            actlearn_tups.append((int(srcid), robjects.globalenv['err.decr'][i-1]))# I tested this, i starts at 0


        allsrc_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        for i, srcid in enumerate(testdata_dict['srcid_list']):
            tups_list = zip(list(robjects.r("rf_clfr$test$votes[%d,]" % (i+1))),  possible_classes)
            tups_list.sort(reverse=True)
            for j in range(3):
                allsrc_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))


        return {'actlearn_tups':actlearn_tups,
                'allsrc_tups':allsrc_tups,
                'py_obj':classifier_out,
                'r_name':'rf_clfr',
                'select':robjects.globalenv['select'],
                'select.pred':robjects.r("rf_clfr$test$predicted[select]"),
                'select.predprob':robjects.r("rf_clfr$test$votes[select,]"),
                'err.decr':robjects.globalenv['err.decr'],
                'all.pred':robjects.r("rf_clfr$test$predicted"),
                'all.predprob':robjects.r("rf_clfr$test$votes"),
                'possible_classes':possible_classes,
                }


    def test_missForest_impuation_error(self, feature_data_dict):
        """ Do imputation of missing-value feature values in dataset

          - See arxiv 1105.0828v1 for more information on
                 the R:MissForest imputation code for R:randomForest()

        This function is used to explore the errors which arrise due to imputation of ASAS data
             for various "ntree" parameter values used in randomForest()
                 
        1 - (40588 / 46057.) = 0.11874416483922101
           -> where 46057 is the number of sources with both NA and non-NA attribs
           -> where 40588 is the number of sources with non-NA attribs
        So we will simulate this NA-source ratio un the 40588 source dataset
            by adding 

        """
        import datetime
        r_data_dict = {}
        for feat_name, feat_longlist in feature_data_dict.items():
            r_data_dict[feat_name] = robjects.FloatVector(feat_longlist)
        features_r_data = robjects.r['data.frame'](**r_data_dict)

        robjects.globalenv['miss_data'] = features_r_data
        robjects.r("""
            miss_data_no_NA = na.omit(miss_data)
            """)
        ntree_list = [300]
        for ntree in ntree_list:
            now = datetime.datetime.now()

            robjects.r("""
                miss_data_generated_NA <- miss_data_no_NA

                ### Here we take the non-NA dataset and force NA in a percentage of sources for all of the color features
                noNA = 0.118744
                n <- nrow(miss_data_generated_NA)
                NAloc <- rep(FALSE, n)
                NAloc[sample(n, floor(n*noNA))] <- TRUE
                miss_data_generated_NA$color_diff_hk[array(NAloc, dim=n)] <- NA
                miss_data_generated_NA$color_diff_jh[array(NAloc, dim=n)] <- NA
                miss_data_generated_NA$color_bv_extinction[array(NAloc, dim=n)] <- NA

                miss_data_generated_NA.imp = missForest(miss_data_generated_NA, mtry=5, ntree=%d)
                err = mixError(miss_data_generated_NA.imp$Ximp, miss_data_generated_NA, miss_data_no_NA)
                """ % (ntree))
            err = float(list(robjects.r('err'))[0])
            fp = open("/home/pteluser/scratch/active_learn/asas_ntree_imputation_tests.dat", "a+")
            fp.write("%d %lf %s\n" % (ntree, err, str(datetime.datetime.now() - now)))
            fp.close()
        import pdb; pdb.set_trace()
        print()


    def generate_imputed_arff_for_ntree(self, feature_data_dict, mtry=None, ntree=None, header_str=None, feature_list=[], srcid_list=[], class_list=[], train_srcids=[]):
        """ given a feature_data_dict and mtrey, ntree params, impute the data set
        and write arff file.

         - To be run on Ipython task node.
        """

        new_feat_dict = self.imputation_using_missForest(feature_data_dict, mtry=mtry, ntree=ntree)

        n_srcs = len(srcid_list)#new_feat_dict[new_feat_dict.keys()[0]])

        train_row_lines = [header_str, "@DATA"]
        test_row_lines = [header_str, "@DATA"]
        for i in range(n_srcs):
            srcid = srcid_list[i]
            if srcid in train_srcids:
                train_row_list = [srcid_list[i]]
                ### We use the ordered feature_list, so that attribs in a row match the order of the header
                for feat_name in feature_list:
                    train_row_list.append(str(new_feat_dict[feat_name][i]))
                train_row_list.append("'%s'" % (class_list[i]))
                new_line = ','.join(train_row_list)
                train_row_lines.append(new_line)
            else:
                test_row_list = [srcid_list[i]]
                ### We use the ordered feature_list, so that attribs in a row match the order of the header
                for feat_name in feature_list:
                    test_row_list.append(str(new_feat_dict[feat_name][i]))
                test_row_list.append("'%s'" % (class_list[i]))
                new_line = ','.join(test_row_list)
                test_row_lines.append(new_line)

        train_arff_str = '\n'.join(train_row_lines)
        train_arff_fpath = "/home/pteluser/scratch/active_learn/imputed_arffs/train_full_%dntree_%dmtry.arff" % (ntree, mtry)
        fp = open(train_arff_fpath, "w")
        fp.write(train_arff_str)
        fp.close()

        test_arff_str = '\n'.join(test_row_lines)
        test_arff_fpath = "/home/pteluser/scratch/active_learn/imputed_arffs/test_full_%dntree_%dmtry.arff" % (ntree, mtry)
        fp = open(test_arff_fpath, "w")
        fp.write(test_arff_str)
        fp.close()

        return {'test_arff_fpath':test_arff_fpath,
                'train_arff_fpath':train_arff_fpath}


    def imputation_using_missForest(self, feature_data_dict, mtry=None, ntree=None):
        """ Do imputation of missing-value feature values in dataset

          - See arxiv 1105.0828v1 for more information on
                 the R:MissForest imputation code for R:randomForest()
        """
        #import numpy
        r_data_dict = {}
        for feat_name, feat_longlist in feature_data_dict.items():
            try:
                r_data_dict[feat_name] = robjects.FloatVector(feat_longlist)
            except:
                print('feat_longlist.count(None)=', feat_longlist.count(None), '\t', feat_name)
                raise # apparently None values are not automatically converted to numpy.nan.  Must do earlier.
            #print feat_longlist.count(numpy.nan), '\t', feat_name
        #import pdb; pdb.set_trace()
        #print
        features_r_data = robjects.r['data.frame'](**r_data_dict)

        robjects.globalenv['miss_data'] = features_r_data

        r_str = "miss_data.imp = missForest(miss_data, verbose=TRUE, mtry=%d, ntree=%d)$Ximp" % ( \
                                                                                 mtry, ntree)
        blah = robjects.r(r_str)

        out_feat_dict = {}
        feature_names = list(robjects.r("names(miss_data.imp)"))
        for i, feat_name in enumerate(feature_names):
            out_feat_dict[feat_name] = list(robjects.r("miss_data.imp$%s" % (feat_name)))

        return out_feat_dict


    def actlearn_randomforest(self, traindata_dict={},
                              testdata_dict={},
                              do_ignore_NA_features=False,
                              ntrees=1000, mtry=25,
                              nfolds=10, nodesize=5,
                              num_srcs_for_users=100,
                              random_seed=0,
                              both_user_match_srcid_bool=[],
                              actlearn_sources_freqsignifs=[]):
        """ Train a randomForest() R classifier

        Taken from class_cv.R : rf.cv (L40)
        """
        if do_ignore_NA_features:
            print("actlearn_randomforest():: do_ignore_NA_features==True not implemented because obsolete")
            raise

        train_featname_longfeatval_dict = traindata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in train_featname_longfeatval_dict.items():
            train_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        traindata_dict['features'] = robjects.r['data.frame'](**train_featname_longfeatval_dict)
        traindata_dict['classes'] = robjects.StrVector(traindata_dict['class_list'])

        robjects.globalenv['xtr'] = traindata_dict['features']
        robjects.globalenv['ytr'] = traindata_dict['classes']
        
        test_featname_longfeatval_dict = testdata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in test_featname_longfeatval_dict.items():
            test_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        testdata_dict['features'] = robjects.r['data.frame'](**test_featname_longfeatval_dict)
        testdata_dict['classes'] = robjects.StrVector(testdata_dict['class_list'])

        robjects.globalenv['xte'] = testdata_dict['features']
        robjects.globalenv['yte'] = testdata_dict['classes']

        #import pdb; pdb.set_trace()
        #print

        #robjects.globalenv['instep'] = robjects.IntVector(actlearn_used_srcids_indicies)
        #robjects.globalenv['incl_tr'] = robjects.BoolVector(both_user_match_srcid_bool)
        robjects.globalenv['actlearn_sources_freqsignifs'] = robjects.FloatVector(actlearn_sources_freqsignifs)
        robjects.globalenv['both_user_match_srcid_bool'] = robjects.BoolVector(both_user_match_srcid_bool)

        #for class_name in testdata_dict['class_list']:
        #    if (('algol' in class_name.lower()) or ('persei' in class_name.lower())):
        #        print '!', class_name
 
        r_str  = '''

    m=%d

    ntrees=%d
    mtry=%d
    nfolds=%d

    ##### ESTIMATE COST FUNCTION FROM AL SAMPLE
    ## function taking AL sample (indicator that label found & freq_signif) to fit model for
    ## cost (prob. manually label) as fxn. of freq_signif (glm)
    getCost = function(sig, labeled){
     cost.fit = glm(labeled~sig,family="binomial") # logistic regression
     #sig.vec = round(min(freqSigAll)):round(max(freqSigAll)) # vector to predict
     sig.vec = 0:ceiling(max(xte[,'freq_signif'])) # 0:38 # vector to predict  (range of freq_signif values in the 50k asas dataset)
     cost.pred = predict(cost.fit,newdata = data.frame(sig=sig.vec),se.fit=TRUE) # prediction

     cost = exp(cost.pred$fit) / (1+exp(cost.pred$fit)) # cost function
     cost.up =  exp(cost.pred$fit+cost.pred$se.fit) / (1+exp(cost.pred$fit+cost.pred$se.fit))
     cost.dn =  exp(cost.pred$fit-cost.pred$se.fit) / (1+exp(cost.pred$fit-cost.pred$se.fit))
     return(list(cost=cost,costUp=cost.up,costDn=cost.dn))
    }

   #al.sel.cost = alSelect(feat.debos,class.deb,feat.asas[1:7000,],m=50,ntrees=500,cost=cost.fxn)


    #cost = getCost(instep,incl_tr,xtr[,'freq_signif'])
    cost = getCost(actlearn_sources_freqsignifs, both_user_match_srcid_bool)
    cost.fxn = cost$cost

    ytr = class.debos(ytr)

    n.tr = length(ytr) # number of training data
    n.te = dim(xte)[1] # number of test data

    if(is.null(mtry)){ mtry = ceiling(sqrt(dim(xtr)[2]))} # set mtry
    #xte.imp = missForest(xte, verbose=TRUE)$Ximp
    #xtr.imp = missForest(xtr, verbose=TRUE)$Ximp # dstarr hack to get rid of training missingvals
    rf_clfr = randomForest(x=xtr,y=ytr,xtest=xte,ntrees=ntrees,mtry=mtry,proximity=TRUE,nodesize=%d)
    rho = rf_clfr$test$proximity # RF proximity matrix, n.tr by n.te matrix

    cat("Selecting best objects\n")
    n.bar = apply(rho[1:n.te,(n.te+1):(n.te+n.tr)],1,sum) # avg. # training data in same terminal node
    p.hat = apply(rf_clfr$test$votes,1,max)
    err.decr = ((1-p.hat)/(n.bar+1)) %srho[1:n.te,1:n.te] # this is Delta V

    # if there is a cost vector, use it to alter err.decr
    if(length(cost.fxn)>0){
      min.fs = round(min(xte[,'freq_signif']))
      freqsig = round(xte[,'freq_signif'])
      te.cost = cost.fxn[freqsig - min.fs + 1]
      err.decr = err.decr*te.cost
    }

    # choose probabalistically:
    select = sample(1:n.te,m,prob=err.decr/sum(err.decr),replace=FALSE)
    #return(list(select=select,select.pred=rf_clfr$test$predicted[select],select.predprob=rf_clfr$test$votes[select,],err.decr=err.decr,all.pred=rf_clfr$test$predicted,all.predprob=rf_clfr$test$votes))

    # # # This is just needed for filling the ASAS catalog tables:
    rf_applied_to_train = randomForest(x=xtr,y=ytr,xtest=xtr,ntrees=ntrees,mtry=mtry,proximity=TRUE,nodesize=%d)
    # # #

        ''' % (num_srcs_for_users, ntrees, mtry, nfolds, nodesize, "%*%", nodesize)

        classifier_out = robjects.r(r_str)

        #robjects.globalenv['pred_forconfmat']
        #robjects.r("rf_clfr$classes")

        possible_classes = robjects.r("rf_clfr$classes")

        '''
        actlearn_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        #for i, srcid in enumerate(data_dict['srcid_list']):
        for i in robjects.globalenv['select']:
            # I think the robjects.globalenv['select'] R array has an index starting at i=1
            #   so this means if R array gives i=999, then this translates srcid_list[i=998]
            #   so this means if R array gives i=1, then this translates srcid_list[i=0]
            srcid = testdata_dict['srcid_list'][i-1]
            tups_list = zip(list(robjects.r("rf_clfr$test$votes[%d,]" % (i))),  possible_classes)
            tups_list.sort(reverse=True)
            for j in range(3):
                actlearn_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
        '''

        actlearn_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        #for i, srcid in enumerate(data_dict['srcid_list']):

        for i in robjects.globalenv['select']:
            # I think the robjects.globalenv['select'] R array has an index starting at i=1
            #   so this means if R array gives i=999, then this translates srcid_list[i=998]
            #   so this means if R array gives i=1, then this translates srcid_list[i=0]
            srcid = testdata_dict['srcid_list'][i-1]# index is python so starts at 0
            actlearn_tups.append((int(srcid), robjects.globalenv['err.decr'][i-1]))# I tested this, i starts at 0


        #import pdb; pdb.set_trace()
        #print
        allsrc_tups = []
        everyclass_tups = []
        trainset_everyclass_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        for i, srcid in enumerate(testdata_dict['srcid_list']):
            tups_list = zip(list(robjects.r("rf_clfr$test$votes[%d,]" % (i+1))),  possible_classes)
            tups_list.sort(reverse=True)
            for j in range(len(tups_list)):
                if j < 3:
                    allsrc_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
                everyclass_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))

        # # # This is just needed for filling the ASAS catalog tables:
        for i, srcid in enumerate(traindata_dict['srcid_list']):
            tups_list = zip(list(robjects.r("rf_applied_to_train$test$votes[%d,]" % (i+1))),  possible_classes)
            tups_list.sort(reverse=True)
            for j in range(len(tups_list)):
                trainset_everyclass_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
        # # #

        #import pdb; pdb.set_trace()
        #print
        return {'actlearn_tups':actlearn_tups,
                'allsrc_tups':allsrc_tups,
                'everyclass_tups':everyclass_tups,
                'trainset_everyclass_tups':trainset_everyclass_tups,
                'py_obj':classifier_out,
                'r_name':'rf_clfr',
                'select':robjects.globalenv['select'],
                'select.pred':robjects.r("rf_clfr$test$predicted[select]"),
                'select.predprob':robjects.r("rf_clfr$test$votes[select,]"),
                'err.decr':robjects.globalenv['err.decr'],
                'all.pred':robjects.r("rf_clfr$test$predicted"),
                'all.predprob':robjects.r("rf_clfr$test$votes"),
                'possible_classes':possible_classes,
                'all_top_prob':robjects.r("apply(rf_clfr$test$votes,1,max)"),
                }


    def get_confident_sources(self, combo_result_dict={}, n_sources_per_class=10, prob_thresh=0.5):
        """ Generate a N-list of confident sources which should be a good representations
        of each science class.
        """
        robjects.globalenv['pred'] = robjects.IntVector(combo_result_dict['all.pred'])
        robjects.globalenv['maxprob'] = robjects.FloatVector(combo_result_dict['all_top_prob'])

        # KLUDGEY
        srcid_list = []
        for str_srcid in combo_result_dict['srcid_list']:
            srcid_list.append(int(str_srcid))
        robjects.globalenv['ID'] = robjects.IntVector(srcid_list)

        r_str  = '''
 m = %d
 probThresh= %f
 whichConf = which(maxprob>probThresh) # only look at sources with maxProb>probThresh
 tabConf = table(pred[whichConf]) # class distribution of confident sources
 confAdd = NULL # sources to add
 for(ii in 1:length(tabConf)){
   if(tabConf[ii]>0){ # cycle thru confident classes
     if(tabConf[ii]<m){
       ind = which(pred[whichConf]==names(tabConf[ii]))
     } else{
       ind = sample(which(pred[whichConf]==names(tabConf[ii])),%d,replace=FALSE)
     }
     confAdd = c(confAdd,ind)
   }
 }
 indAdd = whichConf[confAdd]
 IDAdd = ID[indAdd]
 predAdd = pred[indAdd]

        ''' % (n_sources_per_class, prob_thresh, n_sources_per_class)
        # return(list(IDAdd=IDAdd,predAdd=predAdd,indAdd=indAdd,confFrac = length(whichConf)/length(maxprob)))
        #import pdb; pdb.set_trace()
        #print

        classifier_out = robjects.r(r_str)

        IDAdd = robjects.globalenv['IDAdd']
        predAdd = robjects.globalenv['predAdd']

        print("Chosen high confidence sources:")
        for i, source_id in enumerate(list(IDAdd)):
            print(source_id, list(predAdd)[i])

        # Want to return a list of one source_id from each class, and also a list of the rest.

        class_list = list(predAdd)

        source_for_each_class = []
        all_other_sources = []
        source_for_each_class_classes = []
        for i, source_id in enumerate(list(IDAdd)):
            if not class_list[i] in source_for_each_class_classes:
                source_for_each_class_classes.append(class_list[i])
                source_for_each_class.append(source_id)
            else:
                all_other_sources.append(source_id)

        return {'all_other_sources':all_other_sources,
                'source_for_each_class':source_for_each_class}



    def train_cforest(self, data_dict, do_ignore_NA_features=False,
                           ntrees=1000, mtry=25, nfolds=10, nodesize=5):
        """ Train a cforest() R classifier

        Taken from class_cv.R : rf.cv (L40)
        """
        featname_longfeatval_dict = data_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in featname_longfeatval_dict.items():
            featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        data_dict['features'] = robjects.r['data.frame'](**featname_longfeatval_dict)
        data_dict['classes'] = robjects.StrVector(data_dict['class_list'])

        robjects.globalenv['x'] = data_dict['features']
        robjects.globalenv['y'] = data_dict['classes']
        
        if do_ignore_NA_features:
            feat_trim_str = 'x = as.data.frame(x[,-which(substr(names(x),1,4)=="sdss"   | substr(names(x),1,3)=="ws_")])'
        else:
            feat_trim_str = ''

        r_str = '''
        %s
    y = class.debos(y)

    train = cbind(y,x)

    ntrees=%d
    mtry=%d
    nfolds=%d
    nodesize=%d
    rf_clfr = cforest(y~.,data=train,controls=cforest_control(mtry=mtry,ntree=ntrees,teststat = "quad",replace = TRUE, fraction=0.632))


        ''' % (feat_trim_str, ntrees, mtry, nfolds, nodesize)
        ### NOTE: when no classwt is given, this same prior is calculated, so no need to do it again:
        #n = length(y)
        #prior = table(y)/n
        #rf_clfr = randomForest(x=x,y=y,classwt=prior,mtry=mtry,ntree=ntrees,nodesize=%d)
        #
        #     rf_clfr = randomForest(x=x,y=y)

        classifier_out = robjects.r(r_str)
        #print classifier_out
        return {'py_obj':classifier_out,
                'r_name':'rf_clfr'}



    def apply_randomforest(self, classifier_dict={}, data_dict={},
                           do_ignore_NA_features=False,
                           return_prediction_probs=False,
                           ignore_feats=[]):
        """ Apply the randomforest classifier to some data

        Taken from class_cv.R : rf.cv (L40)
        """
        # TODO: just remove features here:
        featname_longfeatval_dict = data_dict['featname_longfeatval_dict']
        new_featname_longfeatval_dict = {}
        for feat_name, feat_longlist in featname_longfeatval_dict.items():
            if feat_name in ignore_feats:
                continue # skip these
            #print feat_name
            #featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
            new_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        data_dict['features'] = robjects.r['data.frame'](**new_featname_longfeatval_dict)
        data_dict['classes'] = robjects.StrVector(data_dict['class_list'])

        robjects.globalenv['x'] = data_dict['features']
        robjects.globalenv['y'] = data_dict['classes']

        # more obsolete:
        if do_ignore_NA_features:
            #feat_trim_str = 'x = as.data.frame(x[,-which(substr(names(x),1,4)=="sdss"   | substr(names(x),1,3)=="ws_")])'
            feat_trim_str = 'x = as.data.frame(x[,-which(substr(names(x),1,4)=="sdss"   | substr(names(x),1,3)=="ws_")])'
        else:
            feat_trim_str = ''


        ### Im thinking this might have worked due to the training and testing cases having the same number of classes for debosscher?   Maybe during crossvalidation work?  Doesnt seem to work when train and test classes are different:
        r_str__pre20110308 = '''
        %s
    y = class.debos(y)
    n = length(y)
    p = length(table(y))
    
    predictions = matrix(0,nrow=n,ncol=p)
    predictions = predict(%s,newdata=x,type='prob')
    pred = levels(y)[apply(predictions,1,which.max)]
    pred = factor(pred,levels=levels(y))
    confmat = fixconfmat(table(pred,y),levels(pred),names(table(y)))
    err.rate = 1-sum(diag(confmat))/n
        ''' % (feat_trim_str,
               classifier_dict['class_name'])

        # post 20110308: This seems to work, although I think pred_symmetric is useful for {printing pred_symmetric will show the final classification for each source - especially when test and train have different class-sets} only because its definition halfhazardly gives this correct result (due to my hacky knowledge of R).
        r_str = '''
        %s
    y = class.debos(y)
    n = length(y)
    p = length(table(y))
    
    predictions = matrix(0,nrow=n,ncol=p)
    predictions = predict(%s,newdata=x,type='prob')
    #pred_symmetric = factor(rf_clfr$classes[apply(predictions,1,which.max)],levels=rf_clfr$classes) # printing pred_symmetric will show the final classification for each source
    pred_forconfmat = factor(levels(y)[apply(predictions,1,which.max)],levels=levels(y))
    confmat = fixconfmat(table(pred_forconfmat,y),levels(pred_forconfmat),names(table(y)))
    err.rate = 1-sum(diag(confmat))/n
        ''' % (feat_trim_str,
               classifier_dict['class_name'])
        ##OLD##confmat = table(pred,y)
        ###### show the features used in testset & classifier:
        #print numpy.sort(numpy.array(robjects.r('names(x)')))
        #print numpy.sort(numpy.array(robjects.r('rownames(rf.tr$importance)')))
        
        # # # # # NOTE: I since the confmat (ie (pred,y) does not always have m==n, this err.rate is not always correctly calculated
        robjects.r(r_str)
        classifier_error_rate = robjects.globalenv['err.rate']  # 20110308: NOTE: I think err.rate and confmat are only useful when the training and testing datasets have classes from the same set-of-classes.
        robj_confusion_matrix = robjects.globalenv['confmat']
        #WORKS, but this is now R:pred#predicted_classes = robjects.r("rf_clfr$classes[apply(predictions,1,which.max)]")
        #20101227comout#confusion_matrix_axes_classes = robjects.r("levels(pred)")
        predicted_classes = robjects.globalenv['pred_forconfmat']
        possible_classes = robjects.r("%s$classes" % (classifier_dict['r_name']))

        ### 20110308:
        predictions = {}
        if return_prediction_probs:
            predictions['tups'] = []
            #  Nice and kludgey.  Could do this in R if I knew it a bit better
            for i, srcid in enumerate(data_dict['srcid_list']):
                tups_list = zip(list(robjects.r("predictions[%d,]" % (i+1))),  possible_classes)
                tups_list.sort(reverse=True)
                for j in range(3):
                    try:
                        predictions['tups'].append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
                    except:
                        predictions['tups'].append((srcid, j, tups_list[j][0], tups_list[j][1]))
                        
        
        ##### DEBUG
        #print 'Orig clases:', robjects.globalenv['y']
        #print '"pred" final predictions:', robjects.globalenv['pred']
        #print '"predictions" sub-values', robjects.globalenv['predictions']
        #print '"confmat" COnfusion matrix:', robjects.globalenv['confmat']
        #print 'dstarr R predictions:', robjects.r("rf_clfr$classes[apply(predictions,1,which.max)]")

        #print robjects.r("apply(predictions,1,which.max)")
        #1  2  3  4  5 
        #10 11  8 25 25 
        #print robjects.r("levels(y)")
        #[1] "g. RR Lyrae, FM" "i. RR Lyrae, DM" "j. Delta Scuti"  "x. Beta Lyrae"  
        # print robjects.r("rf_clfr$classes")


        ##### KLUDGE: I want the classes which are used in the pred row ordering:
        #cmat_str = str(robjects.r("confmat"))
        #cmat_lines = cmat_str.split('\n')
        #i_end = cmat_lines[0].find('y')
        #confusion_matrix_axes_classes = []
        #for line in cmat_lines[2:]:
        #    if len(line) < 4:
        #        break 
        #    if line[3] == '.':
        #        confusion_matrix_axes_classes.append(line[:i_end].strip())
        #    else:
        #        break
        #####

        #confusion_matrix_axes_classes = list(robjects.r('attributes(confmat)$dimnames$pred'))
        confusion_matrix_axis_pred = list(robjects.r('attributes(confmat)$dimnames$pred'))
        confusion_matrix_axis_y = list(robjects.r('attributes(confmat)$dimnames$y'))

        #print confusion_matrix_axes_classes
        # # # # # # #
        # # # # # # #
        #####
     
        out_dict = {'error_rate':classifier_error_rate[0],
                    'robj_confusion_matrix':robj_confusion_matrix,
                    'predicted_classes':predicted_classes,
                    'predictions':predictions,
                    'possible_classes':possible_classes,
                    'orig_classes':list(robjects.r("levels(y)[y]")),
                    'confusion_matrix_axis_pred':confusion_matrix_axis_pred,
                    'confusion_matrix_axis_y':confusion_matrix_axis_y}

        #print "*** iters_list:", data_dict['iters_list']
        #print "*** percent_list:", data_dict['percent_list']
        #print "*** orig_classes:", out_dict['orig_classes']
        #print "*** predicted_classes:", out_dict['predicted_classes']


        #import pdb; pdb.set_trace()
        #print
        return out_dict


    def apply_randomforest__simple_output(self, classifier_dict={}, data_dict={},
                           return_prediction_probs=False,
                           ignore_feats=[]):
        """ Apply the randomforest classifier to some data

        This simple version allows the data_dict to not have any classes
           and thus no complicated confusion matrix metrics are returned.
        Only prediction percentages, classes are returned.

        Adapted from apply_randomforest()

        Taken from class_cv.R : rf.cv (L40)
        """
        # TODO: just remove features here:
        featname_longfeatval_dict = data_dict['featname_longfeatval_dict']
        new_featname_longfeatval_dict = {}
        for feat_name, feat_longlist in featname_longfeatval_dict.items():
            if feat_name in ignore_feats:
                continue # skip these
            #print feat_name
            #featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
            new_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        data_dict['features'] = robjects.r['data.frame'](**new_featname_longfeatval_dict)
        data_dict['classes'] = robjects.StrVector(data_dict['class_list'])

        robjects.globalenv['x'] = data_dict['features']
        robjects.globalenv['y'] = data_dict['classes']
        #import pdb; pdb.set_trace()
        #print

        r_str = '''
    y = class.debos(y)
    n = length(y)
    p = length(table(y))
    
    predictions = matrix(0,nrow=n,ncol=p)
    predictions = predict(%s,newdata=x,type='prob')
        ''' % (classifier_dict['class_name'])

        # # # # # NOTE: I since the confmat (ie (pred,y) does not always have m==n, this err.rate is not always correctly calculated
        robjects.r(r_str)
        possible_classes = robjects.r("%s$classes" % (classifier_dict['r_name']))

        ### 20110308:
        predictions = {}
        if return_prediction_probs:
            predictions['tups'] = []
            #  Nice and kludgey.  Could do this in R if I knew it a bit better
            for i, srcid in enumerate(data_dict['srcid_list']):
                tups_list = zip(list(robjects.r("predictions[%d,]" % (i+1))),  possible_classes)
                tups_list.sort(reverse=True)
                for j in range(3):
                    try:
                        predictions['tups'].append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
                    except:
                        predictions['tups'].append((srcid, j, tups_list[j][0], tups_list[j][1]))
                        
        out_dict = {'predictions':predictions,
                    'possible_classes':possible_classes,
                    }


        return out_dict



    def apply_cforest(self, classifier_dict={}, data_dict={},
                           do_ignore_NA_features=False):
        """ Apply the R: party:cforest classifier to some data

        Taken from class_cv.R : rf.cv (L85)
        """
        featname_longfeatval_dict = data_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in featname_longfeatval_dict.items():
            featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        data_dict['features'] = robjects.r['data.frame'](**featname_longfeatval_dict)
        data_dict['classes'] = robjects.StrVector(data_dict['class_list'])

        robjects.globalenv['x'] = data_dict['features']
        robjects.globalenv['y'] = data_dict['classes']
        
        if do_ignore_NA_features:
            feat_trim_str = 'x = as.data.frame(x[,-which(substr(names(x),1,4)=="sdss"   | substr(names(x),1,3)=="ws_")])'
        else:
            feat_trim_str = ''

        r_str = '''
        %s
    y = class.debos(y)
    n = length(y)
    p = length(table(y))
    test = cbind(y,x)
    
    predictions = matrix(0,nrow=n,ncol=p)
    predictions = matrix(unlist(treeresponse(%s,newdata=test)),n,p,byrow=T)
    pred = levels(y)[apply(predictions,1,which.max)]
    pred = factor(pred,levels=levels(y))
    confmat = fixconfmat(table(pred,y),levels(pred),names(table(y)))
    err.rate = 1-sum(diag(confmat))/n
        ''' % (feat_trim_str,
               classifier_dict['class_name'])
        ##OLD##confmat = table(pred,y)

        # # # # # NOTE: I since the confmat (ie (pred,y) does not always have m==n, this err.rate is not always correctly calculated
        robjects.r(r_str)
        #import pdb; pdb.set_trace()
        classifier_error_rate = robjects.globalenv['err.rate']
        robj_confusion_matrix = robjects.globalenv['confmat']
        #WORKS, but this is now R:pred#predicted_classes = robjects.r("rf_clfr$classes[apply(predictions,1,which.max)]")
        #20101227comout#confusion_matrix_axes_classes = robjects.r("levels(pred)")
        predicted_classes = robjects.globalenv['pred']
        #20110118 does not work for cforest classifier object#
        #         possible_classes = robjects.r("rf_clfr$classes")
        
        ##### DEBUG
        #print 'Orig clases:', robjects.globalenv['y']
        #print '"pred" final predictions:', robjects.globalenv['pred']
        #print '"predictions" sub-values', robjects.globalenv['predictions']
        #print '"confmat" COnfusion matrix:', robjects.globalenv['confmat']
        #print 'dstarr R predictions:', robjects.r("rf_clfr$classes[apply(predictions,1,which.max)]")

        #print robjects.r("apply(predictions,1,which.max)")
        #1  2  3  4  5 
        #10 11  8 25 25 
        #print robjects.r("levels(y)")
        #[1] "g. RR Lyrae, FM" "i. RR Lyrae, DM" "j. Delta Scuti"  "x. Beta Lyrae"  
        # print robjects.r("rf_clfr$classes")


        ##### KLUDGE: I want the classes which are used in the pred row ordering:
        #cmat_str = str(robjects.r("confmat"))
        #cmat_lines = cmat_str.split('\n')
        #i_end = cmat_lines[0].find('y')
        #confusion_matrix_axes_classes = []
        #for line in cmat_lines[2:]:
        #    if len(line) < 4:
        #        break 
        #    if line[3] == '.':
        #        confusion_matrix_axes_classes.append(line[:i_end].strip())
        #    else:
        #        break
        #####

        #confusion_matrix_axes_classes = list(robjects.r('attributes(confmat)$dimnames$pred'))
        confusion_matrix_axis_pred = list(robjects.r('attributes(confmat)$dimnames$pred'))
        confusion_matrix_axis_y = list(robjects.r('attributes(confmat)$dimnames$y'))

        #print confusion_matrix_axes_classes
        # # # # # # #
        # # # # # # #
        #####
     
        out_dict = {'error_rate':classifier_error_rate[0],
                    'robj_confusion_matrix':robj_confusion_matrix,
                    'predicted_classes':predicted_classes,
                    #'possible_classes':possible_classes,
                    'orig_classes':list(robjects.r("levels(y)[y]")),
                    'confusion_matrix_axis_pred':confusion_matrix_axis_pred,
                    'confusion_matrix_axis_y':confusion_matrix_axis_y}

        #print "*** iters_list:", data_dict['iters_list']
        #print "*** percent_list:", data_dict['percent_list']
        #print "*** orig_classes:", out_dict['orig_classes']
        #print "*** predicted_classes:", out_dict['predicted_classes']


        #import pdb; pdb.set_trace()
        #print
        return out_dict


    def save_classifier(self, classifier_dict={}, fpath=''):
        """ Write R classifier / predictor to file
        """
        r_str = '''
        save(%s, file="%s")
        ''' % (classifier_dict['r_name'], fpath)
        robjects.r(r_str)


    def load_classifier(self, r_name='', fpath=''):
        """ Load a saved R classifier / predictor from file.
        """
        #r_str = '''
        #%s = load(file="%s")
        #''' % (r_name, fpath)
        r_str = '''
        load(file="%s")
        ''' % (fpath)
        robjects.r(r_str)


    def read_randomForest_classifier_into_dict(self, r_name='rf_clfr',
                                               r_classifier_fpath=""):
        """ Parse a randomForest classifier, such as .Rdat file generated by asas_catalog.R.
        Store in a dictionary which is useable by Rpy2classifier style methods.
        """
        #'py_obj':robjects.r("rf_clfr = randomForest(x=x,y=y,mtry=mtry,ntree=ntrees,nodesize=%d)"),
        # NOWORK:            'py_obj':robjects.r('%s = load(file="%s")' % (r_name, r_classifier_fpath)),
        classifier_dict = {'r_name':r_name,
                           'py_obj':robjects.r('load(file="%s")' % (r_classifier_fpath)),
                           'class_name':r_name,
                           }
        # NOTE: see rpy2_classifiers.py:L1170, L351
        return classifier_dict


    def get_crossvalid_errors(self, feature_data_dict={}, ntree=None, mtry=None, random_seed=None, srcid_list=[], class_list=[]):
        """ Do cross-validation, return the errors, results.
        
        # Reference class_cv.R::rf.cv and
        # TCP/Docs/tutorial_rpy.py::classifier_test_randomforest()

        """
        r_data_dict = {}
        for feat_name, feat_longlist in feature_data_dict.items():
            r_data_dict[feat_name] = robjects.FloatVector(feat_longlist)
        features_r_data = robjects.r['data.frame'](**r_data_dict)
        robjects.globalenv['features'] = features_r_data

        classes = robjects.StrVector(class_list)
        robjects.globalenv['classes'] = classes

        ### NOTE: this is adapted from class_cv.R:rf.cv
        r_str = """

x = features
y = class.debos(classes)
n.trees=%d
mtry=%d
nfolds=10
prior=NULL
# don't train on any of the data in testset
# this is to use in the hierarchical classifier
require(randomForest)
set.seed(sample(1:10^5,1))

n = length(y)
p = length(table(y))
folds = sample(1:nfolds,n,replace=TRUE)
predictions = matrix(0,nrow=n,ncol=p)

if(is.null(mtry)){
  mtry = ceiling(sqrt(dim(x)[2]))
}
# default prior: prop. to observed class rates
 if(is.null(prior)){
  prior = table(y)/n
}

for(ii in 1:nfolds){
  #print(paste("fold",ii,"of",nfolds))
  leaveout = which(folds==ii)
  rf.tmp = randomForest(x=as.matrix(x[-leaveout,]),y=y[-leaveout],classwt=prior,mtry=mtry,ntree=n.trees,nodesize=5)
  predictions[leaveout,] = predict(rf.tmp,newdata=x[leaveout,],type='prob')
}
pred = levels(y)[apply(predictions,1,which.max)]
pred = factor(pred,levels=levels(y))
confmat = fixconfmat(table(pred,y),levels(pred),names(table(y)))
err.rate = 1-sum(diag(confmat))/n
""" % (ntree, mtry)
        #err.rate = rf.out$err.rate
        error_rate = robjects.r(r_str)[0]
        return error_rate
                              

class GenerateFoldedClassifiers:
    """ Generate stratified or non-stratified trainingset/to-train datasets.
    Also generate the R classifiers (RandomForest initially)

    """
    def __init__(self):
        pass


    def generate_fold_subset_data(self, full_data_dict={}, 
                                  n_folds=10,
                                  do_stratified=False,
                                  classify_percent=None):
        """ Generate stratified or non-stratified trainingset/to-train datasets.

        Some of the general algorithms here are adapted from:
                  pairwise_classification.py:partition_sciclassdict_into_folds()

        Return:
        [i_fold]['train_data']{???}
                       data_dict['features']  # list
                       data_dict['classes']   # list

        """
        import random

        if n_folds is None:
            min_n_srcs = min(full_data_dict['srcid_list'])
            if min_n_srcs > 10:
                n_folds = 10
            else:
                n_folds = min_n_srcs


        class_indlist = {}
        for i, class_name in enumerate(full_data_dict['class_list']):
            if class_name not in class_indlist:
                class_indlist[class_name]  = []
            class_indlist[class_name].append(i)



        all_fold_dict = {}
        for i in range(n_folds):
            all_fold_dict[i] = {'train_data':{'srcid_list':[],
                                              'featname_longfeatval_dict':{},
                                              'iters_list':[],
                                              'percent_list':[],
                                              'class_list':[],
                                              'arff_rows':[]},
                                'classif_data':{'srcid_list':[],
                                                'featname_longfeatval_dict':{},
                                                'iters_list':[],
                                                'percent_list':[],
                                                'class_list':[],
                                                'arff_rows':[]}}
            for feat_name in full_data_dict['featname_longfeatval_dict'].keys():
                all_fold_dict[i]['train_data']['featname_longfeatval_dict'][feat_name] = []
                all_fold_dict[i]['classif_data']['featname_longfeatval_dict'][feat_name] = []

        if do_stratified:
            ### Stratified case will have to keep track of which srcids were used in each train/classif fold.
            print('do_stratified!!!  Case not coded yet!')
            
            raise
        else:
            for class_name, ind_list in class_indlist.items():
                src_count = len(ind_list)
                if classify_percent is None:
                    n_to_classify = src_count / n_folds # we exclude only 1 point if n_srcs < (n_folds * 2)
                else:
                    n_to_classify = int(src_count * (classify_percent / 100.))

                for i_fold, fold_dict in all_fold_dict.items():
                    random.shuffle(ind_list)
                    sub_range = ind_list[:n_to_classify]
                    for i in sub_range:
                        fold_dict['classif_data']['srcid_list'].append(full_data_dict['srcid_list'][i])
                        for feat_name in full_data_dict['featname_longfeatval_dict'].keys():
                            fold_dict['classif_data']['featname_longfeatval_dict'][feat_name].append( \
                                                 full_data_dict['featname_longfeatval_dict'][feat_name][i])
                        if len(full_data_dict['iters_list']) > 0:
                            fold_dict['classif_data']['iters_list'].append(full_data_dict['iters_list'][i])
                        if len(full_data_dict['percent_list']) > 0:
                            fold_dict['classif_data']['percent_list'].append(full_data_dict['percent_list'][i])
                        fold_dict['classif_data']['class_list'].append(full_data_dict['class_list'][i])
                        if len(full_data_dict['arff_rows']) > 0:
                            fold_dict['classif_data']['arff_rows'].append(full_data_dict['arff_rows'][i])

                    train_inds = filter(lambda x: x not in sub_range, ind_list)
                    for i in train_inds:
                        fold_dict['train_data']['srcid_list'].append(full_data_dict['srcid_list'][i])
                        for feat_name in full_data_dict['featname_longfeatval_dict'].keys():
                            fold_dict['train_data']['featname_longfeatval_dict'][feat_name].append( \
                                                 full_data_dict['featname_longfeatval_dict'][feat_name][i])
                        if len(full_data_dict['iters_list']) > 0:
                            fold_dict['train_data']['iters_list'].append(full_data_dict['iters_list'][i])
                        if len(full_data_dict['percent_list']) > 0:
                            fold_dict['train_data']['percent_list'].append(full_data_dict['percent_list'][i])
                        fold_dict['train_data']['class_list'].append(full_data_dict['class_list'][i])
                        if len(full_data_dict['arff_rows']) > 0:
                            fold_dict['train_data']['arff_rows'].append(full_data_dict['arff_rows'][i])

        return all_fold_dict

        
    def generate_R_randomforest_classifier_rdata(self, train_data={}, 
                                                 classifier_fpath='',
                                                 do_ignore_NA_features=True,
                                                 algorithms_dirpath='',
                                                 ntrees=1000, mtry=25, nfolds=10, nodesize=5,
                                                 classifier_type='randomForest'):
        """ Given fpath for an rdata file, file will be generated and (re)written.
        """
        rc = Rpy2Classifier(algorithms_dirpath=algorithms_dirpath)

        if os.path.exists(classifier_fpath):
            os.system("rm %s" % (classifier_fpath))


        if classifier_type == 'randomForest':
            classifier_dict = rc.train_randomforest(train_data,
                                                do_ignore_NA_features=do_ignore_NA_features,
                                                ntrees=ntrees, mtry=mtry, nfolds=nfolds, nodesize=nodesize)
        elif classifier_type == 'cforest':
            classifier_dict = rc.train_cforest(train_data,
                                                do_ignore_NA_features=do_ignore_NA_features,
                                                ntrees=ntrees, mtry=mtry, nfolds=nfolds, nodesize=nodesize)
        else:
            print('incorrect classifier_type!')
            raise

        rc.save_classifier(classifier_dict=classifier_dict,
                           fpath=classifier_fpath)
        print('WROTE:', classifier_fpath)



if __name__ == '__main__':

    
    ##### Usage example:
    rc = Rpy2Classifier()

    #arff_str = open(os.path.expandvars("$HOME/scratch/full_deboss_20101220.arff")).read()
    arff_str = open(os.path.expandvars("$HOME/scratch/full_deboss_1542srcs_20110106.arff")).read()
    traindata_dict = rc.parse_full_arff(arff_str=arff_str)
    do_ignore_NA_features = False

    #traindata_dict = rc.parse_joey_feature_class_datfile( \
    #                           feature_fpath=os.path.expandvars("$HOME/scratch/features.dat"),
    #                           class_fpath=os.path.expandvars("$HOME/scratch/class.dat"))
    #do_ignore_NA_features = True


    if 1:
        # generate multiple (folded) classifiers:
        import cPickle
        
        Gen_Fold_Classif = GenerateFoldedClassifiers()
        all_fold_data = Gen_Fold_Classif.generate_fold_subset_data(full_data_dict=traindata_dict,
                                                                   n_folds=10,
                                                                   do_stratified=False,
                                                                   classify_percent=40.)

        for i_fold, fold_data in all_fold_data.items():
            classifier_fpath =    os.path.expandvars("$HOME/scratch/classifier_deboss_RF_%d.rdata" % ( \
                                                                                      i_fold))
            src_data_pkl_fpath =  os.path.expandvars("$HOME/scratch/classifier_deboss_RF_%d.srcs.pkl" % ( \
                                                                                      i_fold))
            if os.path.exists(src_data_pkl_fpath):
                os.system('rm ' + src_data_pkl_fpath)
            fp = open(src_data_pkl_fpath, 'wb')
            cPickle.dump({'srcid_list':all_fold_data[i_fold]['classif_data']['srcid_list']},fp,1)
            fp.close()

            Gen_Fold_Classif.generate_R_randomforest_classifier_rdata(train_data=fold_data['train_data'],
                                                     classifier_fpath=classifier_fpath,
                                                     do_ignore_NA_features=do_ignore_NA_features)
        sys.exit()

    else:
        ##### Single classifier case:
        classifier_fpath = os.path.expandvars("$HOME/scratch/test_RF_classifier__crap.rdata")
        if not os.path.exists(classifier_fpath):
            classifier_dict = rc.train_randomforest(traindata_dict,
                                                do_ignore_NA_features=do_ignore_NA_features)
            rc.save_classifier(classifier_dict=classifier_dict,
                               fpath=classifier_fpath)
            print('WROTE:', classifier_fpath)
            sys.exit()
        else:
            r_name='rf_clfr'
            classifier_dict = {'r_name':r_name}
            rc.load_classifier(r_name=r_name,
                               fpath=classifier_fpath)
        


    classif_results = rc.apply_randomforest(classifier_dict=classifier_dict,
                                            data_dict=traindata_dict,
                                            do_ignore_NA_features=do_ignore_NA_features)
    import pdb; pdb.set_trace()

    #TODO:   crossvalid_results = rc.get_crossvalid_errors()

