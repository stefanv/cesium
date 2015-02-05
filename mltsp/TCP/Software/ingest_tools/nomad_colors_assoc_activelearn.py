#!/usr/bin/env python
"""
This code is to explore using active learning to build a
better ASAS <-> nomad source color association classifier.

This uses output .arff from get_colors_for_tutor_sources.py when using:
        best_nomad_sources = GetColorsUsingNomad.generate_nomad_tutor_source_associations(projid=126,
        pkl_fpath=pkl_fpath,
        do_store_nomad_sources_for_classifier=True)

This arrff has the form:
@RELATION ts
@ATTRIBUTE dist NUMERIC
@ATTRIBUTE j_acvs_nomad NUMERIC
@ATTRIBUTE h_acvs_nomad NUMERIC
@ATTRIBUTE k_acvs_nomad NUMERIC
@ATTRIBUTE jk_acvs_nomad NUMERIC
@ATTRIBUTE v_tutor_nomad NUMERIC
@ATTRIBUTE class {'match','not'}
@data

pdb.py on citris cluster:  
     /global/home/users/dstarr/src/install/epd-6.2-2-rh5-x86_64/lib/python2.6/pdb.py nomad_colors_assoc_activelearn.py

"""
from __future__ import print_function
from __future__ import absolute_import
import sys, os
from rpy2.robjects.packages import importr
from rpy2 import robjects
import numpy
import datetime

# These are sources which were in the "test_withsrcid.arff" file,
#    sources which are not classified by the original hardcoded classifier
#    and I now pretend are not decided by some previous active-learning user.
#     - I also made sure there were no missing-value attributes in these lines

def plot_2d(arr, label=''):
    import matplotlib.pyplot as plt
    import numpy as np
    #plt.clf()
    fig = plt.figure()
    ax = fig.add_subplot(111)
    cax = ax.imshow(arr)#, interpolation='nearest')
    ax.set_xlabel(label)
    #plt.savefig("/global/home/users/dstarr/scratch/nomad_asas_acvs_classifier/rho_bot.eps")
    plt.show()
    


class IPython_Task_Administrator:
    """ Send of Imputation tasks

    Adapted from activelearn_utils.py
    Previously Adapted from generate_weka_classifiers.py:Parallel_Arff_Maker()

    """
    def __init__(self, pars={}):
        try:
            from IPython.kernel import client
        except:
            pass

        self.kernel_client = client

        self.pars = pars
        # TODO:             - initialize ipython modules
        self.mec = client.MultiEngineClient()
        #self.mec.reset(targets=self.mec.get_ids()) # Reset the namespaces of all engines
        self.tc = client.TaskClient()
	self.task_id_list = []

        #### 2011-01-21 added:
        self.mec.reset(targets=self.mec.get_ids())
        self.mec.clear_queue()
        self.mec.clear_pending_results()
        self.tc.task_controller.clear()


    def initialize_clients(self, train_fpath='', test_fpath='', testset_indicies=[],
                           classifier_filepath='', r_pars={}):
        """ Instantiate ipython1 clients, import all module dependencies.
        """
	#task_str = """cat = os.getpid()"""
	#taskid = self.tc.run(client.StringTask(task_str, pull="cat"))
	#time.sleep(2)
	#print self.tc.get_task_result(taskid, block=False).results

        # 20090815(before): a = arffify.Maker(search=[], skip_class=False, local_xmls=True, convert_class_abrvs_to_names=False, flag_retrieve_class_abrvs_from_TUTOR=True, dorun=False)
        import time

        
        #sys.path.append(os.environ.get('TCP_DIR') + '/Algorithms')
        #import rpy2_classifiers
        #import rpy2.robjects.numpy2ri
        mec_exec_str = """
import sys, os
sys.path.append(os.environ.get('TCP_DIR') + '/Software/ingest_tools')
import nomad_colors_assoc_activelearn
from rpy2.robjects.packages import importr
from rpy2 import robjects
import numpy
testset_indicies = %s
ncaa = nomad_colors_assoc_activelearn.Nomad_Colors_Assoc_AL()
ncaa.load_data_on_task_engine(classifier_filepath="%s", train_fpath="%s", test_fpath="%s", pars=%s, testset_indicies=testset_indicies)
""" % (str(testset_indicies), classifier_filepath, train_fpath, test_fpath, str(r_pars))
        #self.mec.execute(exec_str)

        print('before mec()')
        #print mec_exec_str
        #import pdb; pdb.set_trace()
        engine_ids = self.mec.get_ids()
        pending_result_dict = {}
        for engine_id in engine_ids:
            pending_result_dict[engine_id] = self.mec.execute(mec_exec_str, targets=[engine_id], block=False)
        n_pending = len(pending_result_dict)
        i_count = 0
        while n_pending > 0:
            still_pending_dict = {}
            for engine_id, pending_result in pending_result_dict.iteritems():
                try:
                    result_val = pending_result.get_result(block=False)
                except:
                    print("get_result() Except. Still pending on engine: %d" % (engine_id))
                    still_pending_dict[engine_id] = pending_result
                    result_val = None # 20110105 added
                if result_val is None:
                    print("Still pending on engine: %d" % (engine_id))
                    still_pending_dict[engine_id] = pending_result
            if i_count > 10:
                self.mec.clear_pending_results()
                pending_result_dict = {}
                self.mec.reset(targets=still_pending_dict.keys())
                for engine_id in still_pending_dict.keys():
                    pending_result_dict[engine_id] = self.mec.execute(mec_exec_str, targets=[engine_id], block=False)
                ###
                time.sleep(20) # hack
                pending_result_dict = [] # hack
                ###
                i_count = 0
            else:
                print("sleeping...")
                time.sleep(5)
                pending_result_dict = still_pending_dict
            n_pending = len(pending_result_dict)
            i_count += 1

        print('after mec()')
        time.sleep(5) # This may be needed, although mec() seems to wait for all the Ipython clients to finish
        print('after sleep()')



class Nomad_Colors_Assoc_AL:
    """ Class for doing the active learning for classifier which associates
    nomad sources to ASAS sources using color & distance based features.

    This is related to get_colors_for_tutor_source.py
    """
    def __init__(self, pars={}):
        self.pars = pars

        algorithms_dirpath = os.path.abspath(os.environ.get("TCP_DIR") + 'Algorithms/')
        sys.path.append(algorithms_dirpath)

        import rpy2_classifiers
        self.rc = rpy2_classifiers.Rpy2Classifier(algorithms_dirpath=algorithms_dirpath)



    def load_arff(self, arff_str, skip_missingval_lines=False, fill_arff_rows=False):
        """ Parse existing arff with Nomad/ASAS color based features
        """
        data_dict = self.rc.parse_full_arff(arff_str=arff_str, skip_missingval_lines=skip_missingval_lines, fill_arff_rows=fill_arff_rows)
        return data_dict


    # OBSOLETE:
    def actlearn_randomforest__singleclassifier(self, traindata_dict={},
                              testdata_dict={},
                              do_ignore_NA_features=False,
                              ntrees=1000, mtry=25,
                              nfolds=10, nodesize=5,
                              num_srcs_for_users=100,
                              random_seed=0,
                              both_user_match_srcid_bool=[],
                              actlearn_sources_freqsignifs=[]):
        """
        This was adapted from:

           rpy2_classifiers.py:actlearn_randomforest():
                  - Train a randomForest() R classifier : Taken from class_cv.R : rf.cv (L40)

        """
        if do_ignore_NA_features:
            print("actlearn_randomforest():: do_ignore_NA_features==True not implemented because obsolete")
            raise



        train_featname_longfeatval_dict = traindata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in train_featname_longfeatval_dict.iteritems():
            #if feat_name == 'dist':
            #    import pdb; pdb.set_trace()
            #    print

            train_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        traindata_dict['features'] = robjects.r['data.frame'](**train_featname_longfeatval_dict)
        traindata_dict['classes'] = robjects.StrVector(traindata_dict['class_list'])

        robjects.globalenv['xtr'] = traindata_dict['features']
        robjects.globalenv['ytr'] = traindata_dict['classes']
        
        test_featname_longfeatval_dict = testdata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in test_featname_longfeatval_dict.iteritems():
            #if feat_name == 'dist':
            #    import pdb; pdb.set_trace()
            #    print
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
    cat("In R code\n")

    m=%d

    ntrees=%d
    mtry=%d
    nfolds=%d

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

        actlearn_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        #for i, srcid in enumerate(data_dict['srcid_list']):

        for i in robjects.globalenv['select']:
            # I think the robjects.globalenv['select'] R array has an index starting at i=1
            #   so this means if R array gives i=999, then this translates srcid_list[i=998]
            #   so this means if R array gives i=1, then this translates srcid_list[i=0]
            srcid = testdata_dict['srcid_list'][i-1]# index is python so starts at 0
            actlearn_tups.append((int(srcid), robjects.globalenv['err.decr'][i-1]))# I tested this, i starts at 0, 2012-03-12 dstarr confirmed


        #import pdb; pdb.set_trace()
        #print
        allsrc_tups = []
        everyclass_tups = []
        trainset_everyclass_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        for i, srcid in enumerate(testdata_dict['srcid_list']):
            tups_list = zip(list(robjects.r("rf_clfr$test$votes[%d,]" % (i+1))),  possible_classes)
            tups_list.sort(reverse=True)
            for j in xrange(len(tups_list)):
                # This stores the prob ordered classifications, for top 3 classes, and seperately for all classes:
                if j < 3:
                    allsrc_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
                everyclass_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))

        # # # This is just needed for filling the ASAS catalog tables:
        for i, srcid in enumerate(traindata_dict['srcid_list']):
            tups_list = zip(list(robjects.r("rf_applied_to_train$test$votes[%d,]" % (i+1))),  possible_classes)
            tups_list.sort(reverse=True)
            for j in xrange(len(tups_list)):
                trainset_everyclass_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
        # # #

        #import pdb; pdb.set_trace()
        #print

        return {'al_probis_match':list(robjects.r('rf_clfr$test$votes[select,][,"match"]')),
                'al_probis_not':list(robjects.r('rf_clfr$test$votes[select,][,"not"]')),
                'al_deltaV':[robjects.globalenv['err.decr'][i-1] for i in list(robjects.globalenv['select'])],
                'al_srcid':[testdata_dict['srcid_list'][i-1] for i in list(robjects.globalenv['select'])],
            }
        """
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
        """


    def actlearn_randomforest(self, traindata_dict={},
                              testdata_dict={},
                              do_ignore_NA_features=False,
                              ntrees=1000, mtry=25,
                              nfolds=10, nodesize=5,
                              num_srcs_for_users=100,
                              random_seed=0,
                              n_predict_parts = 4,
                              both_user_match_srcid_bool=[],
                              actlearn_sources_freqsignifs=[]):
        """
        This was adapted from:

           rpy2_classifiers.py:actlearn_randomforest():
                  - Train a randomForest() R classifier : Taken from class_cv.R : rf.cv (L40)

        """
        if do_ignore_NA_features:
            print("actlearn_randomforest():: do_ignore_NA_features==True not implemented because obsolete")
            raise



        train_featname_longfeatval_dict = traindata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in train_featname_longfeatval_dict.iteritems():
            #if feat_name == 'dist':
            #    import pdb; pdb.set_trace()
            #    print

            train_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        traindata_dict['features'] = robjects.r['data.frame'](**train_featname_longfeatval_dict)
        traindata_dict['classes'] = robjects.StrVector(traindata_dict['class_list'])

        robjects.globalenv['xtr'] = traindata_dict['features']
        robjects.globalenv['ytr'] = traindata_dict['classes']
        
        test_featname_longfeatval_dict = testdata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in test_featname_longfeatval_dict.iteritems():
            #if feat_name == 'dist':
            #    import pdb; pdb.set_trace()
            #    print
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


        ################################################################
        if 0:
            r_str  = '''
    cat("In R code\n")

    m=%d

    ntrees=%d
    mtry=%d
    nfolds=%d

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


    # choose probabalistically:
    select = sample(1:n.te,m,prob=err.decr/sum(err.decr),replace=FALSE)
    #return(list(select=select,select.pred=rf_clfr$test$predicted[select],select.predprob=rf_clfr$test$votes[select,],err.decr=err.decr,all.pred=rf_clfr$test$predicted,all.predprob=rf_clfr$test$votes))

    # # # This is just needed for filling the ASAS catalog tables:
    rf_applied_to_train = randomForest(x=xtr,y=ytr,xtest=xtr,ntrees=ntrees,mtry=mtry,proximity=TRUE,nodesize=%d)
    # # #

        ''' % (num_srcs_for_users, ntrees, mtry, nfolds, nodesize, "%*%", nodesize)
            import pdb; pdb.set_trace()
            print()


            classifier_out = robjects.r(r_str)

            import matplotlib.pyplot as plt
            import numpy as np
            fig = plt.figure()
            ax = fig.add_subplot(111)
            data = numpy.array(robjects.r("rho"))
            cax = ax.imshow(data, interpolation='nearest')
            plt.show()
            import pdb; pdb.set_trace()
            print()
        ################################################################

        

        r_str  = '''
    cat("In R code\n")
    random_seed = %d
    set.seed(random_seed)

    m=%d

    ntrees=%d
    mtry=%d
    nfolds=%d
    nodesize=%d

    nparts=%d

    ytr = class.debos(ytr)

    n.tr = length(ytr) # number of training data
    n.te = dim(xte)[1] # number of test data

    if(is.null(mtry)){ mtry = ceiling(sqrt(dim(xtr)[2]))} # set mtry
    ## ## ## ## ## ## The following builds the proximity matrix and Active-learn derived features in an iterative manner:
    n_p = floor(n.te / nparts) # KLUDGE: misses 1 if not evenly divisable
    ### First iteration (ii=1), so that rho3 is declared:
    #set.seed(random_seed)
    rf_clfr = randomForest(x=xtr,y=ytr,ntrees=ntrees,mtry=mtry,proximity=TRUE,nodesize=nodesize, keep.forest=TRUE)
        ''' % (random_seed, num_srcs_for_users, ntrees, mtry, nfolds, nodesize, n_predict_parts) #, nodesize)
        classifier_out = robjects.r(r_str)

        nte = robjects.r("n.te")[0]
        ntr = robjects.r("n.tr")[0]
        n_p = robjects.r("n_p")[0]

        ### NOTE: I use these lists of arrays in hopes of eventually parallelizing this bit.
        ### even though I am just filling a triangle (half), I just create a nparts x nparts list of lists:
        ###              prox_list[i][j] triangle where j >= i ; contains 2D arrays
        prox_list = []
        votes_list = [] # length n_parts, which in test case is nparts=4, each with with 250x2 arrays
        for i in range(0, n_predict_parts):
            votes_list.append([])
        for i in range(0, n_predict_parts + 1):
            prox_list.append([])
            for j in range(0, n_predict_parts + 1):
                prox_list[i].append([])

        ###loop:   0,1 0,2 0,3 0,tr  1,2 1,3 1,tr   2,3 2,tr
        for i in range(0, n_predict_parts):
            for j in range(i, n_predict_parts + 1):
                print(datetime.datetime.now(), i, j, n_predict_parts, 'n_p:', n_p)
                r_str  = '''
    # starts at 0:
    i=%d
    j=%d
    # xte_part contains the i data at the bottom or first section of rows, j data in the appended data
    xte_bot = xte[((i*n_p)+1):((i+1)*n_p),]

    if(j == nparts){
      xte_top = xtr
    } else {
      xte_top = xte[((j*n_p)+1):((j+1)*n_p),]
    }

    pr = predict(rf_clfr, newdata=rbind(xte_bot,xte_top), proximity=TRUE, norm.votes=FALSE, type='vote', predict.all=TRUE)
    rho_bot = pr$proximity[1:n_p,1:n_p]

    if (j == nparts){
      # this is the case which is convolved with the trainingset
      rho_top = pr$proximity[1:n_p,-(1:n_p)]
    } else {
      rho_top = pr$proximity[(n_p+1):(2*n_p),1:n_p]
    }

    if((i == (nparts-1)) & (j == nparts)){
      rho_tr_cross = pr$proximity[-(1:n_p),-(1:n_p)]
    }
    votes_bot = pr$predicted$aggregate[1:n_p,]
                ''' % (i, j)
                out = robjects.r(r_str)

                if j == i:
                    ### This is the first entry into inner j loop
                    votes_list[i] = numpy.array(robjects.r("votes_bot"))
                    prox_list[i][i] = numpy.array(robjects.r("rho_bot"))
                else:
                    prox_list[i][j] = numpy.array(robjects.r("rho_top"))

                if ((j==n_predict_parts) and (i==n_predict_parts-1)):
                    prox_list[n_predict_parts][n_predict_parts] = numpy.array(robjects.r("rho_tr_cross")) # final corner train x train prox matrix

        
        import pdb; pdb.set_trace()
        print()

        vote_arr = numpy.zeros((nte,2))
        prox_arr = numpy.zeros((nte,nte + ntr))
        for i in range(0, n_predict_parts):
            vote_arr[(i*n_p):(i+1)*n_p,:] = votes_list[i]
            for j in range(i, n_predict_parts + 1):
                if len(prox_list[i][j]) > 0:
                    if j < n_predict_parts:
                        prox_arr[(j*n_p):(j+1)*n_p,(i*n_p):(i+1)*n_p] = prox_list[i][j] # dont do when j >= n_predict_parts
                        if j != i:
                            prox_arr[(i*n_p):(i+1)*n_p,(j*n_p):(j+1)*n_p] = prox_list[i][j].T
                    else:
                        prox_arr[(i*n_p):(i+1)*n_p,(j*n_p):] = prox_list[i][j] # dont do when j >= n_predict_parts

        vote_arr /= float(ntrees) # normalize, which is what was expected in single case: rf_clfr$test$votes

        nbar = numpy.sum(prox_arr[:nte,nte+1:(nte+ntr)],1)
        phat = numpy.max(vote_arr,1)
        #errdecr = ((1-phat)/(nbar+1)) * prox_arr[:nte,:nte] # this is Delta V
        errdecr_mat = numpy.mat((1-phat)/(nbar+1)) * numpy.mat(prox_arr[:nte,:nte])  #(((1-phat)/(nbar+1))).T * prox_arr[:nte,:nte] # this is Delta V
        errdecr = numpy.array(errdecr_mat)[0]
        if 1:
            import matplotlib.pyplot as plt
            import numpy as np
            fig = plt.figure()
            ax = fig.add_subplot(111)
            data = prox_arr
            cax = ax.imshow(data, interpolation='nearest')
            plt.show()
            import pdb; pdb.set_trace()
            print()

        possible_classes = robjects.r("rf_clfr$classes")

        ### Unfortunately I don't know of a python function which does what this does in R:
        #      select = sample(1:n.te,m,prob=err.decr/sum(err.decr),replace=FALSE)
        robjects.globalenv['err.decr'] = robjects.FloatVector(errdecr)
        select = numpy.array(robjects.r("sample(1:n.te,m,prob=err.decr/sum(err.decr),replace=FALSE)"))

        select -= 1 # this makes the indicies in select start from 0 (for use in numpy)


        #import pdb; pdb.set_trace()
        #print

        actlearn_tups = []
        for i in select:
            # minimum i is 1 (not 0)
            # I think the robjects.globalenv['select'] R array has an index starting at i=1
            #   so this means if R array gives i=999, then this translates srcid_list[i=998]
            #   so this means if R array gives i=1, then this translates srcid_list[i=0]
            srcid = testdata_dict['srcid_list'][i]# index is python so starts at 0
            actlearn_tups.append((int(srcid), errdecr[i]))# I tested this, i starts at 0, 2012-03-12 dstarr confirmed


        #import pdb; pdb.set_trace()
        #print
        allsrc_tups = []
        everyclass_tups = []
        trainset_everyclass_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        #import pdb; pdb.set_trace()
        #print
        if 0:
            for i, srcid in enumerate(testdata_dict['srcid_list']):
                #tups_list = zip(list(robjects.r("rf_clfr$test$votes[%d,]" % (i+1))),  possible_classes)
                tups_list = zip(list(vote_arr[i]),  possible_classes)
                tups_list.sort(reverse=True)
                for j in xrange(len(tups_list)):
                    # This stores the prob ordered classifications, for top 3 classes, and seperately for all classes:
                    #if j < 3:
                    #    allsrc_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
                    everyclass_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))

        # # # This is just needed for filling the ASAS catalog tables:
        #for i, srcid in enumerate(traindata_dict['srcid_list']):
        #    tups_list = zip(list(robjects.r("rf_applied_to_train$test$votes[%d,]" % (i+1))),  possible_classes)
        #    tups_list.sort(reverse=True)
        #    for j in xrange(len(tups_list)):
        #        trainset_everyclass_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
        # # #

        #import pdb; pdb.set_trace()
        #print

        #return {'al_probis_match':list(robjects.r('rf_clfr$test$votes[select,][,"match"]')),
        #        'al_probis_not':list(robjects.r('rf_clfr$test$votes[select,][,"not"]')),
        #        'al_deltaV':[robjects.globalenv['err.decr'][i-1] for i in list(robjects.globalenv['select'])],
        #        'al_srcid':[testdata_dict['srcid_list'][i-1] for i in list(robjects.globalenv['select'])],
        #    }
        return {'al_probis_match':[vote_arr[i][0] for i in select],
                'al_probis_not':[vote_arr[i][1] for i in select],
                'al_deltaV':[errdecr[i] for i in select],
                'al_srcid':[testdata_dict['srcid_list'][i] for i in select],
            }
        """
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
        """


    def actlearn_randomforest__load_test_train_data_into_R(self, traindata_dict={},
                              testdata_dict={},
                              do_ignore_NA_features=False,
                              ntrees=1000, mtry=25,
                              nfolds=10, nodesize=5,
                              num_srcs_for_users=100,
                              random_seed=0,
                              n_predict_parts = 4,
                              both_user_match_srcid_bool=[],
                              actlearn_sources_freqsignifs=[]):
        """
        This was adapted from: actlearn_randomforest()
        
        This just loads testdata, traindata, and some params into R
        """
        if do_ignore_NA_features:
            print("actlearn_randomforest():: do_ignore_NA_features==True not implemented because obsolete")
            raise

        train_featname_longfeatval_dict = traindata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in train_featname_longfeatval_dict.iteritems():
            train_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        traindata_dict['features'] = robjects.r['data.frame'](**train_featname_longfeatval_dict)
        traindata_dict['classes'] = robjects.StrVector(traindata_dict['class_list'])

        robjects.globalenv['xtr'] = traindata_dict['features']
        robjects.globalenv['ytr'] = traindata_dict['classes']
        
        test_featname_longfeatval_dict = testdata_dict['featname_longfeatval_dict']
        for feat_name, feat_longlist in test_featname_longfeatval_dict.iteritems():
            test_featname_longfeatval_dict[feat_name] = robjects.FloatVector(feat_longlist)
        testdata_dict['features'] = robjects.r['data.frame'](**test_featname_longfeatval_dict)
        testdata_dict['classes'] = robjects.StrVector(testdata_dict['class_list'])

        robjects.globalenv['xte'] = testdata_dict['features']
        robjects.globalenv['yte'] = testdata_dict['classes']

        robjects.globalenv['actlearn_sources_freqsignifs'] = robjects.FloatVector(actlearn_sources_freqsignifs)
        robjects.globalenv['both_user_match_srcid_bool'] = robjects.BoolVector(both_user_match_srcid_bool)

        r_str  = '''
    cat("In R code\n")
    random_seed = %d
    set.seed(random_seed)

    m=%d

    ntrees=%d
    mtry=%d
    nfolds=%d
    nodesize=%d

    nparts=%d

    ytr = class.debos(ytr)

    n.tr = length(ytr) # number of training data
    n.te = dim(xte)[1] # number of test data

    if(is.null(mtry)){ mtry = ceiling(sqrt(dim(xtr)[2]))} # set mtry
    ## ## ## ## ## ## The following builds the proximity matrix and Active-learn derived features in an iterative manner:
    n_p = floor(n.te / nparts) # KLUDGE: misses 1 if not evenly divisable
        ''' % (random_seed, num_srcs_for_users, ntrees, mtry, nfolds, nodesize, n_predict_parts) #, nodesize)
        classifier_out = robjects.r(r_str)



    def actlearn_randomforest__write_classifier_file(self, classifier_filepath=''):
        """
        This was adapted from:
           actlearn_randomforest()
        """

        r_str = '''
        rf_clfr = randomForest(x=xtr,y=ytr,ntrees=ntrees,mtry=mtry,proximity=TRUE,nodesize=nodesize, keep.forest=TRUE)
        save(rf_clfr, file="%s")
        ''' % (classifier_filepath)
        classifier_out = robjects.r(r_str)


    def actlearn_randomforest__predict_task(self, i=None, j=None, n_predict_parts=None):
        """ This task is to be run within an ipython-parallel engine.
        """
        nte = robjects.r("n.te")[0]
        ntr = robjects.r("n.tr")[0]
        n_p = robjects.r("n_p")[0]
        ntree = robjects.r("ntrees")[0]

        r_str  = '''
    # starts at 0:
    i=%d
    j=%d
    # xte_part contains the i data at the bottom or first section of rows, j data in the appended data
    xte_bot = xte[((i*n_p)+1):((i+1)*n_p),]

    if(j == nparts){
      xte_top = xtr
    } else {
      xte_top = xte[((j*n_p)+1):((j+1)*n_p),]
    }

    pr = predict(rf_clfr, newdata=rbind(xte_bot,xte_top), proximity=TRUE, norm.votes=FALSE, type='vote', predict.all=TRUE)
    rho_bot = pr$proximity[1:n_p,1:n_p]

    if (j == nparts){
      # this is the case which is convolved with the trainingset
      rho_top = pr$proximity[1:n_p,-(1:n_p)]
    } else {
      rho_top = pr$proximity[(n_p+1):(2*n_p),1:n_p]
    }

    if((i == (nparts-1)) & (j == nparts)){
      rho_tr_cross = pr$proximity[-(1:n_p),-(1:n_p)]
    }
    votes_bot = pr$predicted$aggregate[1:n_p,]
                ''' % (i, j)
        out = robjects.r(r_str)

        if 0:
            import matplotlib.pyplot as plt
            import numpy as np
            fig = plt.figure()
            ax = fig.add_subplot(131)
            data = numpy.array(robjects.r("pr$proximity"), dtype=numpy.float32)
            cax = ax.imshow(data)#, interpolation='nearest')
            ax.set_xlabel('pr$proximity')
            #plt.savefig("/global/home/users/dstarr/scratch/nomad_asas_acvs_classifier/rho.eps")

            #plt.clf()
            #fig = plt.figure()
            ax = fig.add_subplot(132)
            data = numpy.array(robjects.r("rho_top"), dtype=numpy.float32)
            cax = ax.imshow(data)#, interpolation='nearest')
            ax.set_xlabel('rho_top')
            #plt.savefig("/global/home/users/dstarr/scratch/nomad_asas_acvs_classifier/rho_top.eps")


            #plt.clf()
            #fig = plt.figure()
            ax = fig.add_subplot(133)
            data = numpy.array(robjects.r("rho_bot"), dtype=numpy.float32)
            cax = ax.imshow(data)#, interpolation='nearest')
            ax.set_xlabel('rho_bot')
            #plt.savefig("/global/home/users/dstarr/scratch/nomad_asas_acvs_classifier/rho_bot.eps")
            plt.show()
            import pdb; pdb.set_trace()
            print()

        #prox_0_dict = {}
        prox_ntree_dict = {}
        prox_else_inds_dict = {}
        prox_else_vals_dict = {}
        prox_else_dict = {}
        votes_dict = {}

        if j == i:
            ### This is the first entry into inner j loop
            votes_dict[i] = numpy.array(robjects.r("votes_bot"))

            rho_flt_arr = numpy.array(robjects.r("rho_bot"), dtype=numpy.float32) * ntree # scaled to ntree so apprx ~int
            ### This generates an INT (0<v<65k) array of proximity counts:
            #rho_int_arr = numpy.around(rho_flt_arr, out=numpy.empty(rho_flt_arr.shape,dtype=numpy.uint16))
            rho_int_arr = numpy.asarray(numpy.around(rho_flt_arr), dtype=numpy.uint16)

            #prox_0 =       rho_int_arr == 0
            prox_ntree =   rho_int_arr == int(ntree)
            else_boolarr = (rho_int_arr > 0) * (rho_int_arr < int(ntree))
            else_vals = rho_int_arr[else_boolarr]
            else_inds = (rho_int_arr * else_boolarr).nonzero() # 2 arrays: i,j index which corresponds to else_vals values

            #prox_0_dict[(i,i)] = prox_0
            prox_ntree_dict[(i,i)] = prox_ntree
            prox_else_inds_dict[(i,i)] = else_inds
            prox_else_vals_dict[(i,i)] = else_vals
            #prox_dict[(i,i)] = numpy.array(robjects.r("rho_bot"), dtype=numpy.float32)
        else:
            rho_flt_arr = numpy.array(robjects.r("rho_top"), dtype=numpy.float32) * ntree # scaled to ntree so apprx ~int
            ### This generates an INT (0<v<65k) array of proximity counts:
            #rho_int_arr = numpy.around(rho_flt_arr, out=numpy.empty(rho_flt_arr.shape,dtype=numpy.uint16))
            rho_int_arr = numpy.asarray(numpy.around(rho_flt_arr), dtype=numpy.uint16)

            #prox_0 =       rho_int_arr == 0
            prox_ntree =   rho_int_arr == int(ntree)
            else_boolarr = (rho_int_arr > 0) * (rho_int_arr < int(ntree))
            else_vals = rho_int_arr[else_boolarr]
            else_inds = (rho_int_arr * else_boolarr).nonzero() # 2 arrays: i,j index which corresponds to else_vals values

            #prox_0_dict[(i,j)] = prox_0
            prox_ntree_dict[(i,j)] = prox_ntree
            prox_else_inds_dict[(i,j)] = else_inds
            prox_else_vals_dict[(i,j)] = else_vals

            #prox_dict[(i,j)] = numpy.array(robjects.r("rho_top"), dtype=numpy.float32)
        if ((j==n_predict_parts) and (i==n_predict_parts-1)):

            rho_flt_arr = numpy.array(robjects.r("rho_tr_cross"), dtype=numpy.float32) * ntree # scaled to ntree so apprx ~int
            ### This generates an INT (0<v<65k) array of proximity counts:
            #rho_int_arr = numpy.around(rho_flt_arr, out=numpy.empty(rho_flt_arr.shape,dtype=numpy.uint16))
            rho_int_arr = numpy.asarray(numpy.around(rho_flt_arr), dtype=numpy.uint16)

            #prox_0 =       rho_int_arr == 0
            prox_ntree =   rho_int_arr == int(ntree)
            else_boolarr = (rho_int_arr > 0) * (rho_int_arr < int(ntree))
            else_vals = rho_int_arr[else_boolarr]
            else_inds = (rho_int_arr * else_boolarr).nonzero() # 2 arrays: i,j index which corresponds to else_vals values

            #prox_0_dict[(n_predict_parts,n_predict_parts)] = prox_0
            prox_ntree_dict[(n_predict_parts,n_predict_parts)] = prox_ntree
            prox_else_inds_dict[(n_predict_parts,n_predict_parts)] = else_inds
            prox_else_vals_dict[(n_predict_parts,n_predict_parts)] = else_vals


            #prox_dict[(n_predict_parts,n_predict_parts)] = numpy.array(robjects.r("rho_tr_cross"), dtype=numpy.float32) # final corner train x train prox matrix
        ######## kludge absorbtion of what was once outside and in task collector:
        if j < n_predict_parts:
            #prox_0_arr[(j*n_p):(j+1)*n_p,(i*n_p):(i+1)*n_p] = prox_0_list[i][j] # dont do when j >= n_predict_parts
            #prox_ntree_arr[(j*n_p):(j+1)*n_p,(i*n_p):(i+1)*n_p] = prox_ntree_list[i][j] # dont do when j >= n_predict_parts
            prox_else_dict[(i,j)] = dict(zip(zip(prox_else_inds_dict[(i,j)][0] + (j*n_p),
                                              prox_else_inds_dict[(i,j)][1] + (i*n_p)), 
                                          prox_else_vals_dict[(i,j)]))

            if j != i:
                #prox_0_arr[(i*n_p):(i+1)*n_p,(j*n_p):(j+1)*n_p] = prox_0_list[i][j].T
                #prox_ntree_arr[(i*n_p):(i+1)*n_p,(j*n_p):(j+1)*n_p] = prox_ntree_list[i][j].T
                prox_else_dict[(i,j)] = dict(zip(zip(prox_else_inds_dict[(i,j)][1] + (i*n_p),
                                                  prox_else_inds_dict[(i,j)][0] + (j*n_p)), 
                                              prox_else_vals_dict[(i,j)]))

        else:
            #prox_0_arr[(i*n_p):(i+1)*n_p,(j*n_p):] = prox_0_list[i][j] 
            #prox_ntree_arr[(i*n_p):(i+1)*n_p,(j*n_p):] = prox_ntree_list[i][j] 
            prox_else_dict[(i,j)] = dict(zip(zip(prox_else_inds_dict[(i,j)][0] + (i*n_p),
                                              prox_else_inds_dict[(i,j)][1] + (j*n_p)), 
                                          prox_else_vals_dict[(i,j)]))

        import cPickle
        fpath = "/global/home/users/dstarr/500GB/nomad_asas_acvs_classifier_pkls/%d_%d.pkl" % (i, j)
        fp = open(fpath, 'wb')
        cPickle.dump(prox_else_dict, fp, 1)
        fp.close()
        #import pdb; pdb.set_trace()
        #print
        return {'prox_ntree_dict':prox_ntree_dict,
                'dict_pkl_fpath_dict':{(i,j):fpath},#'prox_else_inds_dict':prox_else_dict, #prox_else_inds_dict,
                'prox_else_vals_dict':prox_else_vals_dict,
                'votes_dict':votes_dict}#'prox_0_dict':prox_0_dict,


    def load_data_on_task_engine(self, classifier_filepath='',
                                 train_fpath='',
                                 test_fpath='',
                                 testset_indicies=[],
                                 pars={}):
        """ Load the classifier and train & test datasets onto the 
        ipython-parallel task client (presumably in the mec() initialization).
        """
        r_str = '''
        load(file="%s")
        ''' % (classifier_filepath)
        robjects.r(r_str)
        out = self.parse_arff_files(train_fpath=train_fpath, 
                                    test_fpath=test_fpath,
                                    n_test_to_sample=pars['n_test_to_sample'],
                                    testset_indicies=testset_indicies)
        traindata_dict = out['traindata_dict']
        testdata_dict = out['testdata_dict']
        ### This loads traindata, testdata, params into R:
        self.actlearn_randomforest__load_test_train_data_into_R( \
                                                     traindata_dict=traindata_dict,
                                                     testdata_dict=testdata_dict,
                                                     mtry=pars['mtry'],
                                                     ntrees=pars['ntrees'],
                                                     nodesize=pars['nodesize'],
                                                     num_srcs_for_users=pars['num_srcs_for_users'],
                                                     random_seed=pars['random_seed'],
                                                     n_predict_parts=pars['n_predict_parts'])
                                                     
    def wait_for_tasks_to_finish(self):
        """ After spawning ipython tasks, here we wait for the tasks to finish.
        """
        import time
        #prox_0_list = []
        prox_ntree_list = []
        prox_else_inds_list = []
        prox_else_vals_list = []
        prox_else_pkl_list = []

        votes_list = []
        dtime_pending_1 = None
        while ((self.ipy_tasks.tc.queue_status()['scheduled'] > 0) or
               (self.ipy_tasks.tc.queue_status()['pending'] > 0)):
            tasks_to_pop = []
            for task_id in self.ipy_tasks.task_id_list:
                temp = self.ipy_tasks.tc.get_task_result(task_id, block=False)
                if temp is None:
                    continue
                temp2 = temp.results
                if temp2 is None:
                    continue
                results = temp2.get('out_dict',None)
                if results is None:
                    continue # skip some kind of NULL result
                if len(results) > 0:
                    tasks_to_pop.append(task_id)
                    #result_list.append(results) # for some reason I must use the dictionary keys, not just outdict
                    #prox_0_list.append(results['prox_0_dict'])
                    prox_ntree_list.append(results['prox_ntree_dict'])
                    #prox_else_inds_list.append(results['prox_else_inds_dict'])
                    prox_else_pkl_list.append(results['dict_pkl_fpath_dict'])
                    prox_else_vals_list.append(results['prox_else_vals_dict'])
                    votes_list.append(results['votes_dict'])
                    #import pdb; pdb.set_trace()
                    #print

                    #ipython_return_dict = results
                    #update_combo_results(combo_results_dict=combo_results_dict,
                    #                     ipython_return_dict=copy.deepcopy(ipython_return_dict))
            for task_id in tasks_to_pop:
                self.ipy_tasks.task_id_list.remove(task_id)

                
            #    (self.ipy_tasks.tc.queue_status()['pending'] <= 64)):
            #       if ((now - dtime_pending_1) >= datetime.timedelta(seconds=300)):
            if ((self.ipy_tasks.tc.queue_status()['scheduled'] == 0) and 
                (self.ipy_tasks.tc.queue_status()['pending'] <= 7)):
               if dtime_pending_1 is None:
                   dtime_pending_1 = datetime.datetime.now()
               else:
                   now = datetime.datetime.now()
                   if ((now - dtime_pending_1) >= datetime.timedelta(seconds=1200)):
                       print("dtime_pending=1 timeout break!")
                       break
            print(self.ipy_tasks.tc.queue_status())
            print('Sleep... 60', datetime.datetime.utcnow())
            time.sleep(60) #(60)
        # IN CASE THERE are still tasks which have not been pulled/retrieved:
        for task_id in self.ipy_tasks.task_id_list:
            temp = self.ipy_tasks.tc.get_task_result(task_id, block=False)
            if temp is None:
                continue
            temp2 = temp.results
            if temp2 is None:
                continue
            results = temp2.get('out_dict',None)
            if results is None:
                continue #skip some kind of NULL result
            if len(results) > 0:
                tasks_to_pop.append(task_id)
                #result_list.extend(results) # for some reason I must use the dictionary keys, not just outdict
                #prox_0_list.append(results['prox_0_dict'])
                prox_ntree_list.append(results['prox_ntree_dict'])
                #prox_else_inds_list.append(results['prox_else_inds_dict'])
                prox_else_pkl_list.append(results['dict_pkl_fpath_dict'])
                prox_else_vals_list.append(results['prox_else_vals_dict'])
                votes_list.append(results['votes_dict'])
                #ipython_return_dict = results
                #update_combo_results(combo_results_dict=combo_results_dict,
                #                     ipython_return_dict=copy.deepcopy(ipython_return_dict))
        ####
        print(self.ipy_tasks.tc.queue_status())
        return {'prox_ntree_list':prox_ntree_list,
                'prox_else_pkl_list':prox_else_pkl_list,#'prox_else_inds_list':prox_else_inds_list,
                'prox_else_vals_list':prox_else_vals_list,
                'votes_list':votes_list}#'prox_0_list':prox_0_list,


    def actlearn_randomforest__spawn_tasks(self, traindata_dict={},
                                           testdata_dict={},
                                           do_ignore_NA_features=False,
                                           classifier_filepath='',
                                           class_dict={},
                                           train_fpath='',
                                           test_fpath='',
                                           pars={},
                                           do_debug_single_thread=False,
                                           nte=None,
                                           ntr=None,
                                           n_p=None,
                                           ):
        """ This will spawn of predict tasks, which generate sub-components of
        proximity matrix, onto ipython-parallel cluster.
        """


        ###loop:   0,1 0,2 0,3 0,tr  1,2 1,3 1,tr   2,3 2,tr
        for i in range(0, pars['n_predict_parts']):
            for j in range(i, pars['n_predict_parts'] + 1):
                if do_debug_single_thread:
                    ### For debugging:
                    # - this is a combination of the commands found in:
                    #       initialize_clients() & in tc_exec_str below.
                    ncaa = Nomad_Colors_Assoc_AL()
                    ncaa.load_data_on_task_engine(classifier_filepath=classifier_filepath,
                                                  train_fpath=train_fpath,
                                                  test_fpath=test_fpath,
                                                  pars=pars)

                    out_dict = ncaa.actlearn_randomforest__predict_task(i=i, j=j, 
                                                          n_predict_parts=pars['n_predict_parts'])
                    # out_dict:: {'prox_dict':prox_dict, 'votes_arr':votes_arr}
                    # ??? what other params need to be passed in above?

                    import pdb; pdb.set_trace()
                    print()
                    
                else:
                    # NOTE: this is adapted from activelearn_utils.py : L1495
                    tc_exec_str = """
out_dict = ncaa.actlearn_randomforest__predict_task(i=i, j=j, n_predict_parts=n_predict_parts)
                """
                    task_id = self.ipy_tasks.tc.run(self.ipy_tasks.kernel_client.StringTask(tc_exec_str,
                                           push={'i':i,
                                                 'j':j,
                                                 'n_predict_parts':pars['n_predict_parts']},
                                  pull='out_dict', 
                                  retries=3))
                    self.ipy_tasks.task_id_list.append(task_id)

        result_dict = self.wait_for_tasks_to_finish()

        #prox_0_list = []
        prox_ntree_list = []
        #prox_else_inds_list = []
        prox_else_pkl_list = []
        prox_else_vals_list = []
        votes_list = [] # length n_parts, which in test case is nparts=4, each with with 250x2 arrays
        for i in range(0, pars['n_predict_parts']):
            votes_list.append([])
        for i in range(0, pars['n_predict_parts'] + 1):
            #prox_0_list.append([])
            prox_ntree_list.append([])
            #prox_else_inds_list.append([])
            prox_else_pkl_list.append([])
            prox_else_vals_list.append([])
            for j in range(0, pars['n_predict_parts'] + 1):
                #prox_0_list[i].append([])
                prox_ntree_list[i].append([])
                #prox_else_inds_list[i].append([])
                prox_else_pkl_list[i].append([])
                prox_else_vals_list[i].append([])

        for elem in result_dict['prox_ntree_list']:
            for (i,j),prox_array in elem.iteritems():
                prox_ntree_list[i][j] = prox_array

        #for elem in result_dict['prox_else_inds_list']:
        #    for (i,j),prox_array in elem.iteritems():
        #        prox_else_inds_list[i][j] = prox_array
        
        for elem in result_dict['prox_else_pkl_list']:
            for (i,j),prox_array in elem.iteritems():
                prox_else_pkl_list[i][j] = prox_array
        

        for elem in result_dict['prox_else_vals_list']:
            for (i,j),prox_array in elem.iteritems():
                prox_else_vals_list[i][j] = prox_array

        for elem in result_dict['votes_list']:
            for i,vote_array in elem.iteritems():
                votes_list[i] = vote_array

        del(result_dict)

        import scipy.sparse
        vote_arr = numpy.zeros((nte,2), dtype=numpy.float32)
        #prox_0_arr = numpy.zeros((nte,nte + ntr), dtype=numpy.bool)
        prox_ntree_arr = numpy.zeros((nte,nte + ntr), dtype=numpy.bool)
        prox_else_arr = scipy.sparse.dok_matrix((nte,nte + ntr), dtype=numpy.uint16)
        dt_i = datetime.datetime.now()
        dt_prev = datetime.datetime.now()
        import cPickle
        for i in range(0, pars['n_predict_parts']):
            dt_i0 = datetime.datetime.now()
            vote_arr[(i*n_p):(i+1)*n_p,:] = votes_list[i]
            dt_f0 = datetime.datetime.now()
            print('vote_arr[(i*n_p):(i+1)*n_p,:] = votes_list[i]', dt_f0 - dt_i0)

            for j in range(i, pars['n_predict_parts'] + 1):
                dt_now = datetime.datetime.now()
                print(i, j, dt_now - dt_prev)
                dt_prev = dt_now

                fp = open(prox_else_pkl_list[i][j])
                ij_else_dict_tupdict = cPickle.load(fp)#{(0, 0): {(432.0, 939.0): 2, (479.0, 965.0): 449, 
                ij_else_dict = ij_else_dict_tupdict[(i,j)]
                fp.close()

                if j < pars['n_predict_parts']:
                    #prox_0_arr[(j*n_p):(j+1)*n_p,(i*n_p):(i+1)*n_p] = prox_0_list[i][j] # dont do when j >= n_predict_parts
                    prox_ntree_arr[(j*n_p):(j+1)*n_p,(i*n_p):(i+1)*n_p] = prox_ntree_list[i][j] # dont do when j >= n_predict_parts
                    #prox_else_arr.update(prox_else_inds_list[i][j])
                    prox_else_arr.update(ij_else_dict)

                    if j != i:
                        #prox_0_arr[(i*n_p):(i+1)*n_p,(j*n_p):(j+1)*n_p] = prox_0_list[i][j].T
                        prox_ntree_arr[(i*n_p):(i+1)*n_p,(j*n_p):(j+1)*n_p] = prox_ntree_list[i][j].T
                        #prox_else_arr.update(prox_else_inds_list[i][j])
                        prox_else_arr.update(ij_else_dict)

                else:
                    #prox_0_arr[(i*n_p):(i+1)*n_p,(j*n_p):] = prox_0_list[i][j] 
                    prox_ntree_arr[(i*n_p):(i+1)*n_p,(j*n_p):] = prox_ntree_list[i][j] 
                    #prox_else_arr.update(prox_else_inds_list[i][j])
                    prox_else_arr.update(ij_else_dict)

                # free memory?
                #prox_else_inds_list[i][j] = None
                del(ij_else_dict)
                prox_else_vals_list[i][j] = None
                prox_ntree_list[i][j] = None
                #prox_else_arr.todense().dump("/global/home/users/dstarr/scratch/prox.matrixdump")
                #os.system("scp /global/home/users/dstarr/scratch/prox.matrixdump anathem:/tmp/")
                #import pdb; pdb.set_trace()
                #print

        dt_f = datetime.datetime.now()
        print('construction:', dt_f - dt_i)

        dt_i = datetime.datetime.now()
        #prox_sparse = prox_arr.tocsr()
        prox_else_coo = prox_else_arr.tocoo()
        del(prox_else_arr)
        dt_f = datetime.datetime.now()
        print('convert to coo:', dt_f - dt_i)

        dt_i = datetime.datetime.now()
        #prox_sparse = prox_arr.tocsr()
        prox_else_csr = prox_else_coo.tocsr()/float(pars['ntrees'])
        del(prox_else_coo)
        dt_f = datetime.datetime.now()
        print('convert to csr:', dt_f - dt_i)

        if 0:
            ### This is only do-able for small total size proximity matricies:
            #import matplotlib.pyplot as plt
            #import numpy as np
            #fig = plt.figure()
            #ax = fig.add_subplot(111)
            data = numpy.matrix(prox_else_csr.todense() + prox_ntree_arr)
            data.dump("/global/home/users/dstarr/scratch/prox.matrixdump")
            os.system("scp /global/home/users/dstarr/scratch/prox.matrixdump anathem:/tmp/")
            #cax = ax.imshow(data, interpolation='nearest')
            #plt.show()
            #import pdb; pdb.set_trace()
            #print


        # # # #del prox_list # ? helpful? were the inner arrays copied?  or am I just deleting a couple references?

        vote_arr /= float(pars['ntrees']) # normalize, which is what was expected in single case: rf_clfr$test$votes

        dt_i = datetime.datetime.now()
        #prox_elsentree_csr = prox_else_csr + prox_ntree_arr # type(prox_elsentree_csr) <class 'numpy.matrixlib.defmatrix.matrix'> ::: numpy.matrix

        #nbar = numpy.sum(prox_arr[:nte,nte+1:(nte+ntr)],1)
        #CRAP#nbar = prox_sparse[:nte,nte+1:(nte+ntr)].sum(axis=1)
        #nbar = numpy.array(prox_sparse[:nte,nte+1:(nte+ntr)].sum(axis=1))[:,0]
        nbar_1 = numpy.array(prox_else_csr[:nte,nte+1:(nte+ntr)].sum(axis=1), dtype=numpy.float32)[:,0]
        nbar_2 = numpy.array(prox_ntree_arr[:nte,nte+1:(nte+ntr)].sum(axis=1), dtype=numpy.float32)
        nbar = nbar_1 + nbar_2
        dt_f = datetime.datetime.now()
        print('sum:', dt_f - dt_i)
        #import pdb; pdb.set_trace()
        #print

        phat = numpy.max(vote_arr,1)
        #errdecr = ((1-phat)/(nbar+1)) * prox_arr[:nte,:nte] # this is Delta V
        #errdecr_mat = numpy.mat((1-phat)/(nbar+1)) * numpy.mat(prox_arr[:nte,:nte])  #(((1-phat)/(nbar+1))).T * prox_arr[:nte,:nte] # this is Delta V  # MemoryError @ 50000
        dt_i = datetime.datetime.now()
        #errdecr_mat = numpy.mat((1-phat)/(nbar+1)) * prox_sparse[:nte,:nte]  #(((1-phat)/(nbar+1))).T * prox_arr[:nte,:nte] # this is Delta V  # MemoryError @ 50000
        phatnbar = scipy.sparse.lil_matrix((1-phat)/(nbar+1), dtype=numpy.float32)
        dt_f = datetime.datetime.now()
        print('phatnbar LIL def:', dt_f - dt_i)

        dt_i = datetime.datetime.now()
        phatnbar_sparse = phatnbar.tocsr()
        dt_f = datetime.datetime.now()
        print('phatnbar toCSR def:', dt_f - dt_i)

        dt_i = datetime.datetime.now()
        #errdecr_mat = phatnbar_sparse * prox_sparse[:nte,:nte]
        errdecr_mat_1 = phatnbar_sparse * prox_else_csr[:nte,:nte]
        errdecr_mat_2 = phatnbar_sparse * prox_ntree_arr[:nte,:nte]
        errdecr_mat = errdecr_mat_1 + errdecr_mat_2
        dt_f = datetime.datetime.now()
        print('errdecr calc:', dt_f - dt_i)
        #import pdb; pdb.set_trace()
        #print

        #print errdecr.shape
        #(1000,)

        # TODO: I could break the choice() into smaller chuncks, working on smaller arrays
        #    if a memory error occurs here
        #   - if so, will need to then get final selected values

        dt_i = datetime.datetime.now()
        # TODO: todense() is faster?
        #errdecr_arr = errdecr_mat.toarray().ravel() # this is of len(n_test)
        errdecr_arr = numpy.array(errdecr_mat)[0]
        dt_f = datetime.datetime.now()
        print('errdecr_mat.toarray()', dt_f - dt_i)

        dt_i = datetime.datetime.now()
        select = numpy.random.choice(xrange(len(errdecr_arr)),size=pars['num_srcs_for_users'], replace=False, p=errdecr_arr/errdecr_arr.sum())
        dt_f = datetime.datetime.now()
        print('select choice():', dt_f - dt_i)

        #import pdb; pdb.set_trace()
        #print
        #errdecr = numpy.array(errdecr_mat)[0]

        possible_classes = robjects.r("rf_clfr$classes")

        ### Unfortunately I don't know of a python function which does what this does in R:
        #      select = sample(1:n.te,m,prob=err.decr/sum(err.decr),replace=FALSE)
        #robjects.globalenv['err.decr'] = robjects.FloatVector(errdecr)
        #select = numpy.array(robjects.r("sample(1:n.te,m,prob=err.decr/sum(err.decr),replace=FALSE)"))
        #select -= 1 # this makes the indicies in select start from 0 (for use in numpy)
        ## ## ## numpy.random.choice(x,size=2, replace=False, p=x/x.sum())


        #import pdb; pdb.set_trace()
        #print

        actlearn_tups = []
        for i in select:
            # minimum i is 1 (not 0)
            # I think the robjects.globalenv['select'] R array has an index starting at i=1
            #   so this means if R array gives i=999, then this translates srcid_list[i=998]
            #   so this means if R array gives i=1, then this translates srcid_list[i=0]
            srcid = testdata_dict['srcid_list'][i]# index is python so starts at 0
            #actlearn_tups.append((int(srcid), errdecr[i]))# I tested this, i starts at 0, 2012-03-12 dstarr confirmed
            actlearn_tups.append((int(srcid), errdecr_arr[i]))# I tested this, i starts at 0, 2012-03-12 dstarr confirmed


        #import pdb; pdb.set_trace()
        #print
        allsrc_tups = []
        everyclass_tups = []
        trainset_everyclass_tups = []
        #  Nice and kludgey.  Could do this in R if I knew it a bit better
        #import pdb; pdb.set_trace()
        #print
        if 0:
            for i, srcid in enumerate(testdata_dict['srcid_list']):
                #tups_list = zip(list(robjects.r("rf_clfr$test$votes[%d,]" % (i+1))),  possible_classes)
                tups_list = zip(list(vote_arr[i]),  possible_classes)
                tups_list.sort(reverse=True)
                for j in xrange(len(tups_list)):
                    # This stores the prob ordered classifications, for top 3 classes, and seperately for all classes:
                    #if j < 3:
                    #    allsrc_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
                    everyclass_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))

        # # # This is just needed for filling the ASAS catalog tables:
        #for i, srcid in enumerate(traindata_dict['srcid_list']):
        #    tups_list = zip(list(robjects.r("rf_applied_to_train$test$votes[%d,]" % (i+1))),  possible_classes)
        #    tups_list.sort(reverse=True)
        #    for j in xrange(len(tups_list)):
        #        trainset_everyclass_tups.append((int(srcid), j, tups_list[j][0], tups_list[j][1]))
        # # #

        #import pdb; pdb.set_trace()
        #print

        #return {'al_probis_match':list(robjects.r('rf_clfr$test$votes[select,][,"match"]')),
        #        'al_probis_not':list(robjects.r('rf_clfr$test$votes[select,][,"not"]')),
        #        'al_deltaV':[robjects.globalenv['err.decr'][i-1] for i in list(robjects.globalenv['select'])],
        #        'al_srcid':[testdata_dict['srcid_list'][i-1] for i in list(robjects.globalenv['select'])],
        #    }
        return {'al_probis_match':[vote_arr[i][0] for i in select],
                'al_probis_not':[vote_arr[i][1] for i in select],
                'al_deltaV':[errdecr_arr[i] for i in select],
                'al_srcid':[testdata_dict['srcid_list'][i] for i in select],
            }





    def parse_arff_files(self, train_fpath='', test_fpath='', n_test_to_sample=None, testset_indicies=[]):
        """ Parse arff files into expected dict/array scrtuctures
        ##### KLUDGE: initially we exclude all sources which have missing attributes
        #      - so we can do Active learning with imputation
        #      - generally the sources which have missing attributes are non-matches.
        """
        ##### KLUDGE: initially we exclude all sources which have missing attributes
        #      - so we can do Active learning with imputation
        #      - generally the sources which have missing attributes are non-matches.
        train_lines = open(train_fpath).read().split('\n')
        train_lines2 = []
        for line in train_lines:
            if len(line) == 0:
                continue
            if '?' not in line:
                train_lines2.append(line)
        train_str = '\n'.join(train_lines2)

        test_lines = open(test_fpath).read().split('\n')
        test_lines2 = []
        for line in test_lines:
            # each source in this arff has '?' for a class, so we allow for that, but still skip missing attribs
            if line.count('?') <= 0:
                test_lines2.append(line)
        test_str = '\n'.join(test_lines2)
        #####

        # # # # # KLUDGE: we also give unique source_id names that represent NN rank and TUTOR srcid:
        test_lines2 = []
        test_str_split = test_str.split('\n')
        for i, line in enumerate(test_str_split):
            if len(line) == 0:
                new_line = line
            elif line[0] == '@':
                new_line = line
                if line.lower() == '@data':
                    test_lines2.append(new_line)
                    break
            test_lines2.append(new_line)
        i_header_end = i

        import random
        #DEBUG#for i, line in enumerate(test_str_split[i_header_end + 1:n_test_to_sample + i_header_end + 1]):
        #for i, line in enumerate(random.sample(test_str_split[i_header_end + 1:], n_test_to_sample)):
        #for i, line in enumerate(test_str_split[i_header_end + 1:n_test_to_sample + i_header_end + 1]):

        testlines_noheader = test_str_split[i_header_end + 1:]
        if len(testset_indicies) == 0:
            #testset_indicies = range(n_test_to_sample) # DEBUG
            testset_indicies = random.sample(xrange(len(testlines_noheader)), n_test_to_sample)

        for i in testset_indicies:
            line = testlines_noheader[i]
            elems = line.split(',')
            try:
                srcid = "%d%0.2d" % (int(elems[0]), int(elems[2]))
            except:
                print('EXCEPT:', elems, i, line)
                # NOTE: should not have any blank lines in file, or we may get here.
                import pdb; pdb.set_trace()
                print()
            new_line = "%s,%s" % (srcid, ','.join(elems[1:]))
            test_lines2.append(new_line)
        test_str = '\n'.join(test_lines2)


        # # # # #
        
        traindata_dict = self.load_arff(train_str)
        testdata_dict = self.load_arff(test_str, skip_missingval_lines=False, fill_arff_rows=True)
        
        return {'traindata_dict':traindata_dict,
                'testdata_dict':testdata_dict,
                'testset_indicies':testset_indicies}


    def write_summary_dat_files(self, class_dict={},
                                testdata_dict={},
                                i_iter=None, 
                                n_test_to_sample=None, 
                                num_srcs_for_users=None):
        """ Write final output .dat summary files
        """
        
        actlearn_indexes = [testdata_dict['srcid_list'].index(i) for i in class_dict['al_srcid']]
        al_arffrows = [testdata_dict['arff_rows'][i] for i in actlearn_indexes]
        
        out_fpath = os.path.expandvars('$HOME/scratch/nomad_asas_acvs_classifier/al_iter%d_ntest%d_nal%d.dat' % (i_iter, n_test_to_sample, num_srcs_for_users))
        out_fp = open(out_fpath, 'w')
        out_rows = []
                                       
        for i, arffrow in enumerate(al_arffrows):
            out_str =  "dV: %0.3f  M: %0.3f  NOT: %0.3f  %s\n" % (class_dict['al_deltaV'][i],
                                                                class_dict['al_probis_match'][i],
                                                                class_dict['al_probis_not'][i],
                                                                arffrow)
            out_fp.write(out_str)
            out_rows.append(out_str)
        out_fp.close()

        out_rows.sort(reverse=True)
        
        out_fpath = os.path.expandvars('$HOME/scratch/nomad_asas_acvs_classifier/al_iter%d_ntest%d_nal%d__sorted.dat' % (i_iter, n_test_to_sample, num_srcs_for_users))
        out_fp = open(out_fpath, 'w')
        for out_str in out_rows:
            out_fp.write(out_str)
        out_fp.close()


    def main(self, train_fpath='', test_fpath='', 
             i_iter=None,
             n_test_to_sample=None,
             num_srcs_for_users=None,
             n_predict_parts=None,
             random_seed=None):
        """ Main method for initially prototyping this class.
        """

        # TODO: ignore sources which have missing values, for now.
        #    -> TODO: we will train a general RF classifier which allows missing-values in test data
        out = self.parse_arff_files(train_fpath=train_fpath, 
                              test_fpath=test_fpath,
                                    n_test_to_sample=n_test_to_sample)
        traindata_dict = out['traindata_dict']
        testdata_dict = out['testdata_dict']


        ### The following lists contain a combination of sources:
        ###     - all training sources, and previous Active Learning trained sources
        ###     - sources which users recently attempted to classify for an
        ###         active learning iteration, including unsure/non-consensus ([False]) sources
        both_user_match_srcid_bool = [True] * len(traindata_dict['featname_longfeatval_dict']['dist'])# list of [True]
        actlearn_sources_freqsignifs = traindata_dict['featname_longfeatval_dict']['dist'] # list of cost metrics

        # ** TODO: need to add some ambiguoius sources?
        #       - ??? from the test_withsrcid.arff file?

        class_dict = self.actlearn_randomforest(traindata_dict=traindata_dict,
                                                     testdata_dict=testdata_dict,
                                                     mtry=5,
                                                     ntrees=500,
                                                     nodesize=5,
                                                     num_srcs_for_users=num_srcs_for_users,
                                                     random_seed=random_seed,
                                                     both_user_match_srcid_bool=both_user_match_srcid_bool,
                                                     actlearn_sources_freqsignifs=actlearn_sources_freqsignifs,
                                                     n_predict_parts=n_predict_parts,
                                                     )

        self.write_summary_dat_files(class_dict=class_dict,
                                     testdata_dict=testdata_dict,
                                     i_iter=i_iter, 
                                     n_test_to_sample=n_test_to_sample, 
                                     num_srcs_for_users=num_srcs_for_users)



        import pdb; pdb.set_trace()
        print()


    def run_parallel(self, train_fpath='', test_fpath='', 
                     classifier_filepath='',
                     pars={}, do_debug_single_thread=False):
        """ This spawns and controls a parallelized version of actlearn_randomforest()
         - some code adapted from:  rpy2_classifiers.py & activelearn_utils.py

         - This is a parallelized version of main()
        """

        # TODO: ignore sources which have missing values, for now.
        #    -> TODO: we will train a general RF classifier which allows missing-values in test data
        out = self.parse_arff_files(train_fpath=train_fpath, 
                                    test_fpath=test_fpath,
                                    n_test_to_sample=pars['n_test_to_sample'])
        traindata_dict = out['traindata_dict']
        testdata_dict = out['testdata_dict']
        testset_indicies = out['testset_indicies']

        ### The following lists contain a combination of sources:
        ###     - all training sources, and previous Active Learning trained sources
        ###     - sources which users recently attempted to classify for an
        ###         active learning iteration, including unsure/non-consensus ([False]) sources
        #both_user_match_srcid_bool = [True] * len(traindata_dict['featname_longfeatval_dict']['dist'])# list of [True]
        #actlearn_sources_freqsignifs = traindata_dict['featname_longfeatval_dict']['dist'] # list of cost metrics


        # TODO: want to write out the random forest classifier so that it can be used by 
        #       ipython task clients
        self.actlearn_randomforest__load_test_train_data_into_R( \
                                                     traindata_dict=traindata_dict,
                                                     testdata_dict=testdata_dict,
                                                     mtry=pars['mtry'],
                                                     ntrees=pars['ntrees'],
                                                     nodesize=pars['nodesize'],
                                                     num_srcs_for_users=pars['num_srcs_for_users'],
                                                     random_seed=pars['random_seed'],
                                                     n_predict_parts=pars['n_predict_parts'])
                                                     
        class_dict = self.actlearn_randomforest__write_classifier_file( \
                                                     classifier_filepath=classifier_filepath)

        nte = robjects.r("n.te")[0]
        ntr = robjects.r("n.tr")[0]
        n_p = robjects.r("n_p")[0]
        print('nte:', nte, 'ntr:', ntr, 'n_p:', n_p)
        if int(nte) != pars['n_test_to_sample']:
            print("Hit the weird case where R misses one data point in dataframe")
            import pdb; pdb.set_trace()
            print()

        if not do_debug_single_thread: 
            self.ipy_tasks = IPython_Task_Administrator()
            self.ipy_tasks.initialize_clients(train_fpath=train_fpath, 
                                              test_fpath=test_fpath, 
                                              testset_indicies=testset_indicies,
                                              classifier_filepath=classifier_filepath,
                                              r_pars=pars)

        class_dict = self.actlearn_randomforest__spawn_tasks( \
                                                     traindata_dict=traindata_dict,
                                                     testdata_dict=testdata_dict,
                                                     classifier_filepath=classifier_filepath,
                                                     class_dict=class_dict,
                                                     train_fpath=train_fpath,
                                                     test_fpath=test_fpath,
                                                     pars=pars,
                                                     do_debug_single_thread=do_debug_single_thread,
                                                     nte=nte,
                                                     ntr=ntr,
                                                     n_p=n_p,
                                                )

        self.write_summary_dat_files(class_dict=class_dict,
                                     testdata_dict=testdata_dict,
                                     i_iter=pars['i_iter'], 
                                     n_test_to_sample=pars['n_test_to_sample'], 
                                     num_srcs_for_users=pars['num_srcs_for_users'])

        import pdb; pdb.set_trace()
        print()


class Analyze_Nomad_Features:
    """ This is used for analyzing the errors/distributions of NOMAD based features.
    """
    def __init__(self, pars={}):
        self.pars = pars


    def analyze_feat_distribs(self, train_fpath='', test_fpath=''):
        """ To answer MACC paper referee comments, need to analyze feature distribution.

        TODO: want to resample within errors of features, and see how this affects the classifier.
        
        - geenrate histograms of feature distributions for the marked-up training data.

        """
        import matplotlib.pyplot as pyplot
        #get_colors_for_tutor L2034

        out = self.parse_arff_files(train_fpath=train_fpath, 
                              test_fpath=test_fpath,
                                    n_test_to_sample=n_test_to_sample)
        traindata_dict = out['traindata_dict']
        testdata_dict = out['testdata_dict']

        class_array = numpy.array(traindata_dict['class_list'])
        index_not = numpy.where(class_array != 'not')
        index_match = numpy.where(class_array != 'match')
        
        for feat_name, feat_list in traindata_dict['featname_longfeatval_dict'].iteritems():
            feat_array = numpy.array(feat_list)

            #print class_array[index_not]
            x_range = (min(feat_array), max(feat_array))

            fig = pyplot.figure()
            ax = fig.add_subplot('111')

            pyplot.hist(feat_array[index_not], bins=50, facecolor='r', alpha=0.3, range=x_range, normed=False, label='not')
            pyplot.hist(feat_array[index_match], bins=50, facecolor='g', alpha=0.3, range=x_range, normed=False, label='match')
            title_str = '%s' % (feat_name)
            pyplot.title(title_str)
            ax.legend(loc=2)
            pyplot.show()
            import pdb; pdb.set_trace()
            print()
            pyplot.clf()


    def get_nomad_sources_for_ra_dec(self, ra=None, dec=None,
                                     avg_epoch=None,
                                     require_jhk=True):
        """
        Example query:
           findnomad1 304.1868910 -0.7529220 -E 1998.1 -rs 60 -m 30 -lmJ 15.-16.
           -m num results to retrieve
           -rs arcsec radius query
           
        Adapted from code:
        get_colors_for_tutor_sources.py::get_nomad_sources_for_ra_dec()
        """
        self.pars.update({'nomad_radius':120, # 60
                          'nomad_n_results':30})
        
        flags  =[]
        if avg_epoch != None:
            flags.append("-E %d" % (avg_epoch))

        if dec < 0:
            dec_str = str(dec)
        else:
            dec_str = '+' + str(dec)

        exec_str = "findnomad1 %lf %s -rs %d -m %d %s" % (ra, dec_str, self.pars['nomad_radius'],
                                                           self.pars['nomad_n_results'],
                                                           ' '.join(flags))
        import datetime
        
        ti = datetime.datetime.now()
        (a,b,c) = os.popen3(exec_str)
        a.close()
        c.close()
        print(exec_str)
        lines_str = b.read()
        b.close()

        tf = datetime.datetime.now()
        print(tf - ti)
        return lines_str
    

    def parse_nomad_data_lines(self, lines_str, require_jhk=True):
        """  Parses nomad info, includeing positional, propermotion errors.
        Adapted from code:
        get_colors_for_tutor_sources.py::get_nomad_sources_for_ra_dec()
        """

        out_dict = {'dist':[],
                    'B':[],
                    'V':[],
                    'R':[],
                    'J':[],
                    'H':[],
                    'K':[],
                    'ra':[],
                    'dec':[],
                    'ra_err_mas':[], #sRA,sDE     = Mean Error on (RAcos(DE)) and (DE) at mean Epoch (milliarcsecs)
                    'dec_err_mas':[],
                    'pm_err_ra_mas':[],
                    'pm_err_dec_mas':[],
                    }

        lines = lines_str.split('\n')
        for line in lines:
            if len(line) == 0:
                continue
            if line[0] == '#':
                continue
            elems = line.split('|')

            radec_tup_long = elems[2].split()
            if '-' in radec_tup_long[0]:
                radec_tup = radec_tup_long[0].split('-')
                ra_nomad_src = float(radec_tup[0])
                dec_nomad_src = -1. * float(radec_tup[1])
            elif '+' in radec_tup_long[0]:
                radec_tup = radec_tup_long[0].split('+')
                ra_nomad_src = float(radec_tup[0])
                dec_nomad_src = float(radec_tup[1])
            else:
                raise # there should be a ra, dec in the nomad string

            ra_mas = float(radec_tup_long[2])/numpy.cos(dec_nomad_src*numpy.pi/180.)
            dec_mas = float(radec_tup_long[3])

            ### Proper motion error, considering NOMAD returns J2000.
            epoch_data = 2000.  # NOMAD returns J2000 by default
            epochs_tup = elems[3].split()
            epoch_ra = float(epochs_tup[0])
            epoch_dec = float(epochs_tup[1])

            propmot_tups = elems[4].split()
            #  TODO: Are errors over time considered independent and add in quadrature?
            propmot_err_ra_masyear = float(propmot_tups[2])
            propmot_err_ra_mas = propmot_err_ra_masyear * abs(epoch_data-epoch_ra)/numpy.cos(dec_nomad_src*numpy.pi/180.)

            propmot_err_dec_masyear = float(propmot_tups[3])
            propmot_err_dec_mas = propmot_err_dec_masyear * abs(epoch_data-epoch_dec)

            color_str_list = []
            corr_str = elems[5].replace(' T ', '  ').replace(' Y ', '  ')
            for m_str in corr_str.split():
                color_str_list.append(m_str[:-1])
            color_str_list.extend(elems[6].split())
            #print line
            if len(color_str_list) != 6:
                import pdb; pdb.set_trace()
                print() # DEBUG ONLY
                continue

            mag_dict = {}
            for i_band, band_name in enumerate(['B', 'V', 'R', 'J', 'H', 'K']):
                if '--' in color_str_list[i_band]:
                    mag_dict[band_name] = None
                else:
                    mag_dict[band_name] = float(color_str_list[i_band])
    
            dist_str = elems[8][elems[8].find(';')+1:]
            dist = float(dist_str.strip())


            if require_jhk:
                if ((mag_dict['J'] is None) or (mag_dict['H'] is None) or (mag_dict['K'] is None)):
                    continue # skip this source
                
            
            out_dict['ra'].append(ra_nomad_src)
            out_dict['dec'].append(dec_nomad_src)
            out_dict['ra_err_mas'].append(ra_mas)
            out_dict['dec_err_mas'].append(dec_mas)
            out_dict['pm_err_ra_mas'].append(propmot_err_ra_mas)
            out_dict['pm_err_dec_mas'].append(propmot_err_dec_mas)
            out_dict['dist'].append(dist)
            out_dict['B'].append(mag_dict['B'])
            out_dict['V'].append(mag_dict['V'])
            out_dict['R'].append(mag_dict['R'])
            out_dict['J'].append(mag_dict['J'])
            out_dict['H'].append(mag_dict['H'])
            out_dict['K'].append(mag_dict['K'])
                        
        return out_dict  # NOTE: the order should be by distance from given source


    def retrieve_full_nomad_info_for_acvs_sources(self, projid_list=[126], nomad_source_pkl_fpath='',
                                                  nomad_data_cache_dirpath='',
                                                  nomad_radius=120,
                                                  nomad_n_results=30):
        """ Originally we only parsed a subset of information in
                get_colors_for_tutor_sources.py::get_nomad_sources_for_ra_dec()
        This code retrieves all nomad information, so that postitional errors can be analyzed.
        """
        import cPickle
        if not os.path.exists(nomad_source_pkl_fpath):
            from .get_colors_for_tutor_sources import Get_Colors_Using_Nomad, Database_Utils
            GetColorsUsingNomad = Get_Colors_Using_Nomad(pars=pars)
            all_source_dict = GetColorsUsingNomad.get_source_dict(projid_list=projid_list)

            self.pars.update({'nomad_radius':nomad_radius, # 60
                              'nomad_n_results':nomad_n_results})
            out_dict = {}
            for i, src_id in enumerate(all_source_dict['srcid_list']):
                ra = all_source_dict['ra_list'][i]
                dec = all_source_dict['dec_list'][i]
                nomad_fpath = "%s/%d.dat" % (nomad_data_cache_dirpath, src_id)
                if not os.path.exists(nomad_fpath):
                    print(i, src_id)
                    nomad_outstr = self.get_nomad_sources_for_ra_dec(ra=ra, dec=dec,
                                                                    avg_epoch=None)
                    fp = open(nomad_fpath, 'w')
                    fp.write(nomad_outstr)
                    fp.close()
                else:
                    fp = open(nomad_fpath)
                    nomad_outstr = fp.read()
                    fp.close()
                nomad_sources = self.parse_nomad_data_lines(nomad_outstr,
                                                                    require_jhk=True)
                nomad_sources['ra_query'] = ra
                nomad_sources['dec_query'] = dec
                out_dict[src_id] = nomad_sources
            fp = open(nomad_source_pkl_fpath, 'wb')
            cPickle.dump(out_dict, fp, 1)
            fp.close()
        else:
            fp = open(nomad_source_pkl_fpath)
            out_dict = cPickle.load(fp)
            fp.close()
        return out_dict


    # OBSOLETE:
    def retrieve_full_nomad_info_for_linear_sources(self, nomad_source_pkl_fpath='',
                                                  nomad_data_cache_dirpath='',
                                                  nomad_radius=120,
                                                  nomad_n_results=30):
        """ Originally we only parsed a subset of information in
                get_colors_for_tutor_sources.py::get_nomad_sources_for_ra_dec()
        This code retrieves all nomad information, so that postitional errors can be analyzed.

        Adapted from retrieve_full_nomad_info_for_acvs_sources()
        """
        import cPickle
        if not os.path.exists(nomad_source_pkl_fpath):
            from .get_colors_for_tutor_sources import Get_Colors_Using_Nomad, Database_Utils
            GetColorsUsingNomad = Get_Colors_Using_Nomad(pars=pars)
            all_source_dict = GetColorsUsingNomad.get_linear_source_dict_from_tcpdb()
            import pdb; pdb.set_trace()
            print()

            self.pars.update({'nomad_radius':nomad_radius, # 60
                              'nomad_n_results':nomad_n_results})
            out_dict = {}
            for i, src_id in enumerate(all_source_dict['srcid_list']):
                ra = all_source_dict['ra_list'][i]
                dec = all_source_dict['dec_list'][i]
                nomad_fpath = "%s/%d.dat" % (nomad_data_cache_dirpath, src_id)
                if not os.path.exists(nomad_fpath):
                    print(i, src_id)
                    nomad_outstr = self.get_nomad_sources_for_ra_dec(ra=ra, dec=dec,
                                                                    avg_epoch=None)
                    fp = open(nomad_fpath, 'w')
                    fp.write(nomad_outstr)
                    fp.close()
                else:
                    fp = open(nomad_fpath)
                    nomad_outstr = fp.read()
                    fp.close()
                nomad_sources = self.parse_nomad_data_lines(nomad_outstr,
                                                                    require_jhk=True)
                nomad_sources['ra_query'] = ra
                nomad_sources['dec_query'] = dec
                out_dict[src_id] = nomad_sources
            fp = open(nomad_source_pkl_fpath, 'wb')
            cPickle.dump(out_dict, fp, 1)
            fp.close()
        else:
            fp = open(nomad_source_pkl_fpath)
            out_dict = cPickle.load(fp)
            fp.close()
        return out_dict


    def incrementally_retrieve_full_nomad_info_for_linear_sources(self, nomad_source_pkl_fpath='',
                                                  nomad_data_cache_dirpath='',
                                                  nomad_radius=120,
                                                  nomad_n_results=30,
                                                  return_outdict=False):
        """ Originally we only parsed a subset of information in
                get_colors_for_tutor_sources.py::get_nomad_sources_for_ra_dec()
        This code retrieves all nomad information, so that postitional errors can be analyzed.

        Adapted from retrieve_full_nomad_info_for_acvs_sources()
        """
        import cPickle
        #if not os.path.exists(nomad_source_pkl_fpath):
        from .get_colors_for_tutor_sources import Get_Colors_Using_Nomad, Database_Utils
        GetColorsUsingNomad = Get_Colors_Using_Nomad(pars=pars)
        do_loop = True
        while do_loop:
            all_source_dict = GetColorsUsingNomad.get_linear_source_dict_from_tcpdb()
            if len(all_source_dict['srcid_list']) == 0:
                break # no more sources to retrieve.
            #import pdb; pdb.set_trace()
            #print

            self.pars.update({'nomad_radius':nomad_radius, # 60
                              'nomad_n_results':nomad_n_results})
            out_dict = {}
            for i, src_id in enumerate(all_source_dict['srcid_list']):
                ra = all_source_dict['ra_list'][i]
                dec = all_source_dict['dec_list'][i]
                nomad_fpath = "%s/%d.dat" % (nomad_data_cache_dirpath, src_id)
                if not os.path.exists(nomad_fpath):
                    print(i, src_id)
                    nomad_outstr = self.get_nomad_sources_for_ra_dec(ra=ra, dec=dec,
                                                                    avg_epoch=None)
                    fp = open(nomad_fpath, 'w')
                    fp.write(nomad_outstr)
                    fp.close()
                else:
                    if return_outdict:
                        fp = open(nomad_fpath)
                        nomad_outstr = fp.read()
                        fp.close()
                if return_outdict:
                    nomad_sources = self.parse_nomad_data_lines(nomad_outstr,
                                                                    require_jhk=True)
                    nomad_sources['ra_query'] = ra
                    nomad_sources['dec_query'] = dec
                    out_dict[src_id] = nomad_sources
            GetColorsUsingNomad.update_table_retrieved(sourcename_list=all_source_dict['srcid_list'])
            #fp = open(nomad_source_pkl_fpath, 'wb')
            #cPickle.dump(out_dict, fp, 1)
            #fp.close()
        #else:
        #    fp = open(nomad_source_pkl_fpath)
        #    out_dict = cPickle.load(fp)
        #    fp.close()
        return out_dict



    def retrieve_full_nomad_info_for_200k_linear_sources(self, 
                                                  nomad_data_cache_dirpath='',
                                                  nomad_radius=120,
                                                  nomad_n_results=30,
                                                  return_outdict=False):
        """ This retrieves full nomad data for 200k LINEAR sources
        related to the Starvars project.
        
        Adapted from incrementally_retrieve_full_nomad_info_for_linear_sources()
        """
        starvars_200k_ref_fpath = '/Data/dstarr/Data/starvars/masterMain.dat.txt'
        names = ['sdss_ra', 'sdss_dec', 'ra', 'dec', 'objectID', 'objtype', 'mag_median', 'rExt', 'noSATUR', 'uMod', 'gMod', 'rMod', 'iMod', 'zMod', 'uErr', 'gErr', 'rErr', 'iErr', 'zErr', 'J', 'H', 'K', 'JErr', 'HErr', 'KErr', 'stdev', 'rms', 'chi2pdf', 'nObs', 'skew', 'kurt', 'p1', 'phi1', 'p2', 'phi2', 'p3', 'phi3', 'spec', 'RRc', 'Rchi2pdf']
        ref_data = numpy.genfromtxt(starvars_200k_ref_fpath, delimiter=" ", names=names)
        objids = numpy.asarray(ref_data['objectID'], dtype=numpy.int)
        #import pdb; pdb.set_trace()
        #print

        # TODO for objids , check that not in database, then retrieve
        
        import cPickle
        #if not os.path.exists(nomad_source_pkl_fpath):
        from .get_colors_for_tutor_sources import Get_Colors_Using_Nomad, Database_Utils
        GetColorsUsingNomad = Get_Colors_Using_Nomad(pars=pars)
        n_obj_per_iter = 100
        for i_low in range(0, len(objids), n_obj_per_iter):
            id_dataset_unchecked = objids[i_low:i_low + n_obj_per_iter]
            all_source_dict = GetColorsUsingNomad.get_uningested_source_dict_from_tcp(id_dataset_unchecked)

            #all_source_dict = GetColorsUsingNomad.get_linear_source_dict_from_tcpdb()
            if len(all_source_dict['srcid_list']) == 0:
                continue
            #import pdb; pdb.set_trace()sdt
            #print

            self.pars.update({'nomad_radius':nomad_radius, # 60
                              'nomad_n_results':nomad_n_results})
            out_dict = {}
            for i, src_id in enumerate(all_source_dict['srcid_list']):
                ra = all_source_dict['ra_list'][i]
                dec = all_source_dict['dec_list'][i]
                nomad_fpath = "%s/%d.dat" % (nomad_data_cache_dirpath, src_id)
                if not os.path.exists(nomad_fpath):
                    print(i, src_id)
                    nomad_outstr = self.get_nomad_sources_for_ra_dec(ra=ra, dec=dec,
                                                                    avg_epoch=None)
                    fp = open(nomad_fpath, 'w')
                    fp.write(nomad_outstr)
                    fp.close()
                else:
                    if return_outdict:
                        fp = open(nomad_fpath)
                        nomad_outstr = fp.read()
                        fp.close()
                if return_outdict:
                    nomad_sources = self.parse_nomad_data_lines(nomad_outstr,
                                                                    require_jhk=True)
                    nomad_sources['ra_query'] = ra
                    nomad_sources['dec_query'] = dec
                    out_dict[src_id] = nomad_sources
            GetColorsUsingNomad.update_table_retrieved(sourcename_list=all_source_dict['srcid_list'])
            #fp = open(nomad_source_pkl_fpath, 'wb')
            #cPickle.dump(out_dict, fp, 1)
            #fp.close()
        #else:
        #    fp = open(nomad_source_pkl_fpath)
        #    out_dict = cPickle.load(fp)
        #    fp.close()
        return out_dict


    def retrieve_nomad_for_asas_kepler_sources(self, all_source_dict={},
                                                  nomad_data_cache_dirpath='',
                                                  nomad_radius=120,
                                                  nomad_n_results=30,
                                                  return_outdict=False,
                                               pars={}):
        """
        Adapted from retrieve_full_nomad_info_for_200k_linear_sources()

        This retrieves full nomad data for 200k LINEAR sources
        related to the Starvars project.
        
        Adapted from incrementally_retrieve_full_nomad_info_for_linear_sources()
        """
        #starvars_200k_ref_fpath = '/Data/dstarr/Data/starvars/masterMain.dat.txt'
        #names = ['sdss_ra', 'sdss_dec', 'ra', 'dec', 'objectID', 'objtype', 'mag_median', 'rExt', 'noSATUR', 'uMod', 'gMod', 'rMod', 'iMod', 'zMod', 'uErr', 'gErr', 'rErr', 'iErr', 'zErr', 'J', 'H', 'K', 'JErr', 'HErr', 'KErr', 'stdev', 'rms', 'chi2pdf', 'nObs', 'skew', 'kurt', 'p1', 'phi1', 'p2', 'phi2', 'p3', 'phi3', 'spec', 'RRc', 'Rchi2pdf']
        #ref_data = numpy.genfromtxt(starvars_200k_ref_fpath, delimiter=" ", names=names)
        #objids = numpy.asarray(ref_data['objectID'], dtype=numpy.int)
        objids = numpy.asarray(all_source_dict['objids'], dtype=numpy.int)
        #import pdb; pdb.set_trace()
        #print

        # TODO for objids , check that not in database, then retrieve
        
        import cPickle
        #if not os.path.exists(nomad_source_pkl_fpath):
        from .get_colors_for_tutor_sources import Get_Colors_Using_Nomad #, Database_Utils
        GetColorsUsingNomad = Get_Colors_Using_Nomad(pars=pars)
        #n_obj_per_iter = 100
        #for i_low in range(0, len(objids), n_obj_per_iter):
        #    id_dataset_unchecked = objids[i_low:i_low + n_obj_per_iter]
        #    #all_source_dict = GetColorsUsingNomad.get_uningested_source_dict_from_tcp(id_dataset_unchecked)

        #    #all_source_dict = GetColorsUsingNomad.get_linear_source_dict_from_tcpdb()
        #    if len(all_source_dict['srcid_list']) == 0:
        #        continue
        if 1:

            self.pars.update({'nomad_radius':nomad_radius, # 60
                              'nomad_n_results':nomad_n_results})
            out_dict = {}
            for i, src_id in enumerate(all_source_dict['srcid_list']):
                ra = all_source_dict['ra_list'][i]
                dec = all_source_dict['dec_list'][i]
                nomad_fpath = "%s/%s.dat" % (nomad_data_cache_dirpath, src_id)
                if not os.path.exists(nomad_fpath):
                    print(i, src_id)
                    nomad_outstr = self.get_nomad_sources_for_ra_dec(ra=ra, dec=dec,
                                                                    avg_epoch=None)
                    fp = open(nomad_fpath, 'w')
                    fp.write(nomad_outstr)
                    fp.close()
                else:
                    if return_outdict:
                        fp = open(nomad_fpath)
                        nomad_outstr = fp.read()
                        fp.close()
                if return_outdict:
                    nomad_sources = self.parse_nomad_data_lines(nomad_outstr,
                                                                    require_jhk=True)
                    nomad_sources['ra_query'] = ra
                    nomad_sources['dec_query'] = dec
                    out_dict[src_id] = nomad_sources
            #GetColorsUsingNomad.update_table_retrieved(sourcename_list=all_source_dict['srcid_list'])
            #fp = open(nomad_source_pkl_fpath, 'wb')
            #cPickle.dump(out_dict, fp, 1)
            #fp.close()
        #else:
        #    fp = open(nomad_source_pkl_fpath)
        #    out_dict = cPickle.load(fp)
        #    fp.close()

        return out_dict


    def generate_random_position_distances(self, sources_dict):
        """ Use ra, dec errors and proper motion errors to generate
        resampled positions, in order to later test the effectivness of the
        NOMAD source association classifier.

        This returns an update sources_dict.

        Convert milliarcsec errors to degrees using 1000.*60*60 = 3600000.0
        """
        import cPickle
        if not os.path.exists(self.pars['noisif_nomad_colors_for_macc_pkl_fpath']):
            for src_id, source_dict in sources_dict.iteritems():
                for i, ra in enumerate(source_dict['ra']):
                    new_ra = ra 
                    ra_err = source_dict['ra_err_mas'][i]/3600000.0
                    ra_pm_err = source_dict['pm_err_ra_mas'][i]/3600000.0
                    ra_err_combo = 0.
                    if ra_err > 0.:
                        ra_err_combo = numpy.power(ra_err, 2.)
                    if ra_pm_err > 0.:
                        ra_err_combo += numpy.power(ra_pm_err, 2.)
                    if ra_err_combo > 0:
                        new_ra += numpy.random.normal(loc=0., scale=numpy.sqrt(ra_err_combo))

                    new_dec = source_dict['dec'][i]
                    dec_err = source_dict['dec_err_mas'][i]/3600000.0
                    dec_pm_err = source_dict['pm_err_dec_mas'][i]/3600000.0
                    dec_err_combo = 0.
                    if dec_err > 0.:
                        dec_err_combo = numpy.power(dec_err, 2.)
                    if dec_pm_err > 0.:
                        dec_err_combo += numpy.power(dec_pm_err, 2.)
                    if dec_err_combo > 0:
                        new_dec += numpy.random.normal(loc=0., scale=numpy.sqrt(dec_err_combo))

                    new_dist = numpy.sqrt(((new_ra - source_dict['ra_query'])**2.)*numpy.cos(new_dec*numpy.pi/180.) + \
                                          (new_dec - source_dict['dec_query'])**2.) * 3600.
                    #print "new=%f old=%f" % (new_dist, source_dict['dist'][i])

                    source_dict['dist'][i] = new_dist
                    source_dict['ra'][i] = new_ra
                    source_dict['dec'][i] = new_dec
                    
            import cPickle
            fp = open(self.pars['noisif_nomad_colors_for_macc_pkl_fpath'], 'wb')
            cPickle.dump(sources_dict, fp, 1)
            fp.close()
        else:
            fp = open(self.pars['noisif_nomad_colors_for_macc_pkl_fpath'])
            sources_dict = cPickle.load(fp)
            fp.close()
        return sources_dict


    def compare_classifier_crossmatched_with_trainchosen_arff(self, 
            crossmatch_classified_fpath='', # this was filled earlier using RF classifier crossmatch
            train_groundtruth_fpath=''):
        """ Compare the final classes of ground-truth dataset which was user classified
        using Active Learning, with classes generated by crossmatching RandomForest classifier.
        The results should give an idea of the influence that the ra,dec position noisified NOMAD sources
        have on the resulting classifier.
        """

        ncaa = Nomad_Colors_Assoc_AL(pars=pars)
        
        train_groundtruth_dict = ncaa.load_arff(open(train_groundtruth_fpath).read(),
                                                    skip_missingval_lines=False, fill_arff_rows=False)
        crossmatch_classified_dict = ncaa.load_arff(open(crossmatch_classified_fpath).read(),
                                                    skip_missingval_lines=False, fill_arff_rows=False)
        
        count_same_match = 0
        count_same_not = 0
        count_different = 0
        for i, gt_src_id in enumerate(train_groundtruth_dict['srcid_list']):
            # This is the initial index of the matching srcid:
            if not gt_src_id in crossmatch_classified_dict['srcid_list']:
                print("CROSSMATCH CLASSIFIER DOESNT have source:", gt_src_id)
                continue
            j_crossmatch = crossmatch_classified_dict['srcid_list'].index(gt_src_id)
            match_found = False
            for j_offset, cm_src_id in enumerate(crossmatch_classified_dict['srcid_list'][j_crossmatch:]):
                j = j_crossmatch + j_offset

                if gt_src_id != cm_src_id:
                    break

                if (((train_groundtruth_dict['featname_longfeatval_dict']['jk_acvs_nomad'][i] - \
                    crossmatch_classified_dict['featname_longfeatval_dict']['jk_acvs_nomad'][j]) == 0) and
                    ((train_groundtruth_dict['featname_longfeatval_dict']['v_tutor_nomad'][i] == \
                    crossmatch_classified_dict['featname_longfeatval_dict']['v_tutor_nomad'][j]))):
                    #print "%s dist:gt=%f cm=%f j:gt=%f cm=%f gt=%s cm=%s" % (gt_src_id,
                    #               train_groundtruth_dict['featname_longfeatval_dict']['dist'][i],
                    #               crossmatch_classified_dict['featname_longfeatval_dict']['dist'][j],
                    #               train_groundtruth_dict['featname_longfeatval_dict']['j_acvs_nomad'][i],
                    #               crossmatch_classified_dict['featname_longfeatval_dict']['j_acvs_nomad'][j],
                    #               train_groundtruth_dict['class_list'][i],
                    #               crossmatch_classified_dict['class_list'][j])
                    match_found = True
                    if train_groundtruth_dict['class_list'][i] == crossmatch_classified_dict['class_list'][j]:
                        if train_groundtruth_dict['class_list'][i] == 'match':
                            count_same_match += 1
                        elif train_groundtruth_dict['class_list'][i] == 'not':
                            count_same_not += 1
                    else:
                        count_different += 1
                        print("DIFFCLASS: %s dist:gt=%f cm=%f j:gt=%f cm=%f gt=%s cm=%s" % (gt_src_id,
                                   train_groundtruth_dict['featname_longfeatval_dict']['dist'][i],
                                   crossmatch_classified_dict['featname_longfeatval_dict']['dist'][j],
                                   train_groundtruth_dict['featname_longfeatval_dict']['j_acvs_nomad'][i],
                                   crossmatch_classified_dict['featname_longfeatval_dict']['j_acvs_nomad'][j],
                                   train_groundtruth_dict['class_list'][i],
                                   crossmatch_classified_dict['class_list'][j]))

                    break
            if not match_found:
                print("NO MATCH %s dist:gt=%f v_diff:gt=%s jk_diff:gt=%f j:gt=%f gt=%s" % (gt_src_id,
                                   train_groundtruth_dict['featname_longfeatval_dict']['dist'][i],
                                   str(train_groundtruth_dict['featname_longfeatval_dict']['v_tutor_nomad'][i]),
                                   train_groundtruth_dict['featname_longfeatval_dict']['jk_acvs_nomad'][i],
                                   train_groundtruth_dict['featname_longfeatval_dict']['j_acvs_nomad'][i],
                                   train_groundtruth_dict['class_list'][i]))
                #import pdb; pdb.set_trace()
                #print
                
        print("count_same_match=%d count_same_not=%d count_different=%d" % (count_same_match, count_same_not, count_different))
        import pdb; pdb.set_trace()
        print()

                # TODO: match the JHK, and then make sure classes match
            

        #out = ncaa.parse_arff_files(train_fpath=train_groundtruth_fpath, 
        #                            test_fpath=crossmatch_classified_fpath,
        #                            n_test_to_sample=n_test_to_sample)




if __name__ == '__main__':

    pars = { \
        'tcp_hostname':'192.168.1.25',
        'tcp_username':'pteluser',
        'tcp_port':     3306, 
        'tcp_database':'source_test_db',
        'tutor_hostname':'192.168.1.103', #'lyra.berkeley.edu',
        'tutor_username':'dstarr', #'tutor', # guest
        'tutor_password':'ilove2mass', #'iamaguest',
        'tutor_database':'tutor',
        'tutor_port':3306,
        # From get_colors_for_tutor_sources.py:  (OBSOLETE):
        'fpath_train_withsrcid':"/home/dstarr/scratch/nomad_asas_acvs_classifier/train_withsrcid.arff",
        'fpath_train_no_srcid':"/home/dstarr/scratch/nomad_asas_acvs_classifier/train_no_srcid.arff",
        'fpath_test_withsrcid':"/home/dstarr/scratch/nomad_asas_acvs_classifier/test_withsrcid.arff",
        'fpath_test_no_srcid':"/home/dstarr/scratch/nomad_asas_acvs_classifier/test_no_srcid.arff",
        # For Nomad feature analysis:
        'nomad_data_cache_dirpath':'/home/dstarr/scratch/nomad_asas_acvs_classifier/nomad_cache',
        'poserr_nomad_colors_for_macc_pkl_fpath':'/home/dstarr/scratch/nomad_asas_acvs_classifier/poserr_nomad_colors_for_macc.pkl',
        'noisif_nomad_colors_for_macc_pkl_fpath':'/home/dstarr/scratch/nomad_asas_acvs_classifier/noisf_nomad_colors_for_macc.pkl',
        'nomad_assoc_cuts':{'LIBERAL':{'1st_dist':   30,
                                       '1st_dJ':     3.0,
                                       '1st_dJK':    3.0,
                                       '1st_tut-nom':3.0,
                                       '2nd_dist':   -1,
                                       '2nd_tut-nom':0.1,
                                       '3rd_dist':   -1,
                                       '3rd_dJ':     0.1,
                                       '3rd_dJK':    0.1,
                                       '3rd_tut-nom':0.1},
                            'HIPPARCOS':{'1st_dist':   1.0,
                                         '1st_dJ':     0.1,
                                         '1st_dJK':    0.3,
                                         '1st_tut-nom':0.3,
                                         '2nd_dist':   0.1,
                                         '2nd_tut-nom':1.6,
                                         '3rd_dist':   4.25, #2.0,
                                         '3rd_dJ':     0.1,
                                         '3rd_dJK':    0.3,
                                         '3rd_tut-nom':1.6},
                            'OGLE':{'1st_dist':   -1, #25,
                                    '1st_dJ':     0.1,
                                    '1st_dJK':    0.02,
                                    '1st_tut-nom':-1,
                                    '2nd_dist':   0.2, # only couple OGLE pass this cut and their tut-nom <1.45 when <3 tried
                                    '2nd_tut-nom':1.45,
                                    '3rd_dist':   3,   # < 13 has a large peak around 12, which is probably unrelated sources with similar J
                                    '3rd_dJ':     0.02,
                                    '3rd_dJK':    0.02,
                                    '3rd_tut-nom':1.45},#0.75}
                            'ASAS':{'1st_dist':   5.0, # -1 dist disables a group of cuts
                                    '1st_dJ':     0.1,
                                    '1st_dJK':    0.1,
                                    '1st_tut-nom':1.2,
                                    '2nd_dist':   0.75,
                                    '2nd_tut-nom':3.0,
                                    '3rd_dist':  30.0,
                                    '3rd_dJ':     0.1,
                                    '3rd_dJK':    0.1,
                                    '3rd_tut-nom':1.2},
                            },
        }

    train_fpath = os.path.expandvars('$HOME/scratch/nomad_asas_acvs_classifier/train_chosen.arff')
    test_fpath  = os.path.expandvars('$HOME/scratch/nomad_asas_acvs_classifier/notchosen_withclass_withsrcid.arff')
    classifier_filepath = os.path.expandvars('$HOME/scratch/nomad_asas_acvs_classifier/rf_trained_classifier.robj')


    i_iter = 10  # active learning iteration
    n_test_to_sample=30000 #40000  # 50000 is too much (MemoryError at errdecr_mat = numpy.mat((1-phat)/(nbar+1)) * numpy.mat(prox_arr[:nte,:nte])
    n_items_per_task = 2000 #2000   # should evenly divide n_test_to_sample
    num_srcs_for_users=10000 #5000
    random_seed = 1234

    """ MEM 27.7  36:07.13 python (112 engines) & 19.6  17:11.02 python
    i_iter = 6  # active learning iteration
    n_test_to_sample=20000 #40000  # 50000 is too much (MemoryError at errdecr_mat = numpy.mat((1-phat)/(nbar+1)) * numpy.mat(prox_arr[:nte,:nte])
    n_items_per_task = 2000 #2000   # should evenly divide n_test_to_sample
    num_srcs_for_users=5000 #5000
    random_seed = 1234
    """

    if 0:
        # Starvars LINEAR 200K ingestion:
        nomad_data_cache_dirpath = '/home/dstarr/scratch/nomad_linear_classifier/nomad_cache'

        anf = Analyze_Nomad_Features(pars=pars)
        sources_dict = anf.retrieve_full_nomad_info_for_200k_linear_sources( \
                              nomad_data_cache_dirpath=nomad_data_cache_dirpath,
                              nomad_radius=60, # 60
                              nomad_n_results=20,
                              return_outdict=False)
        import pdb; pdb.set_trace()
        print()


    if 1:
        ### LINEAR - NOMAD source association for full LINEAR dataset
        nomad_source_pkl_fpath = '/home/dstarr/scratch/nomad_linear_classifier/nomad_source.pkl'
        nomad_data_cache_dirpath = '/home/dstarr/scratch/nomad_linear_classifier/nomad_cache'

        anf = Analyze_Nomad_Features(pars=pars)
        os.system("rm %s" % (nomad_source_pkl_fpath))
        sources_dict = anf.incrementally_retrieve_full_nomad_info_for_linear_sources( \
                              nomad_source_pkl_fpath=nomad_source_pkl_fpath,
                              nomad_data_cache_dirpath=nomad_data_cache_dirpath,
                              nomad_radius=60, # 60
                              nomad_n_results=20,
                              return_outdict=False)
        


        import pdb; pdb.set_trace()
        print()
    if 0:
        ### LINEAR - NOMAD source association for ~7K linear sources in TUTOR):
        anf = Analyze_Nomad_Features(pars=pars)
        sources_dict = anf.retrieve_full_nomad_info_for_acvs_sources(projid_list=[127],
                              nomad_source_pkl_fpath='/home/dstarr/scratch/nomad_linear_classifier/nomad_source.pkl',
                              nomad_data_cache_dirpath='/home/dstarr/scratch/nomad_linear_classifier/nomad_cache',
                                                                     nomad_radius=60, # 60
                                                                     nomad_n_results=20)
        


        import pdb; pdb.set_trace()
        print()

    n_predict_parts= int(n_test_to_sample / n_items_per_task) #20

    ncaa = Nomad_Colors_Assoc_AL(pars=pars)
    if 1:
        ### This is used for analyzing the errors/distributions of NOMAD based features.
        anf = Analyze_Nomad_Features(pars=pars)
        sources_dict = anf.retrieve_full_nomad_info_for_acvs_sources(projid_list=[126],
                              nomad_source_pkl_fpath=pars['poserr_nomad_colors_for_macc_pkl_fpath'],
                              nomad_data_cache_dirpath=pars['nomad_data_cache_dirpath'],
                                                                     nomad_radius=120, # 60
                                                                     nomad_n_results=30)
        import pdb; pdb.set_trace()
        print()
        #######sources_dict = {}
        sources_dict = anf.generate_random_position_distances(sources_dict)
        if 0:
            ### Fill the ~/scratch/nomad_asas_acvs_classifier/train_withsrcid.arff file with classifier crossmatch assocations using the acvs/nomad features .pkl file generated above.
            pars['classifier_filepath'] = classifier_filepath
            from .get_colors_for_tutor_sources import Get_Colors_Using_Nomad, Database_Utils
            GetColorsUsingNomad = Get_Colors_Using_Nomad(pars=pars)

            from .tutor_database_project_insert import ASAS_Data_Tools
            ASASDataTools = ASAS_Data_Tools(pars={'source_data_fpath':os.path.abspath(os.environ.get("TCP_DIR") + \
                                                'Data/allstars/ACVS.1.1')})
            asas_ndarray = ASASDataTools.retrieve_parse_asas_acvs_source_data()

            GetColorsUsingNomad.generate_nomad_tutor_source_associations(projid=126,
                                                     pkl_fpath=pars['noisif_nomad_colors_for_macc_pkl_fpath'],
                                                     do_store_nomad_sources_for_classifier=True,
                                                                         asas_ndarray=asas_ndarray)

        anf.compare_classifier_crossmatched_with_trainchosen_arff(
            crossmatch_classified_fpath=pars['fpath_train_withsrcid'], # this was filled above using RF classifier crossmatch
            train_groundtruth_fpath=train_fpath,
            )

        # TODO: want to classify sources in sources_dict

        
        ### plot the derived feature distributions:
        #anf.analyze_feat_distribs(train_fpath=train_fpath, 
        #                           test_fpath=test_fpath)
        
        import pdb; pdb.set_trace()
        print()


    if 0:
        ### single core:
        ncaa.main(train_fpath=train_fpath, 
                  test_fpath=test_fpath, 
                  i_iter=i_iter,
                  n_test_to_sample=n_test_to_sample,
                  num_srcs_for_users=num_srcs_for_users,
                  n_predict_parts=n_predict_parts,
                  random_seed=random_seed)
    if 0:
        ### Parallel:
        parallel_pars = { \
            'i_iter':i_iter,
            'mtry':5,
            'ntrees':500,
            'nodesize':5,
            'num_srcs_for_users':num_srcs_for_users,
            'random_seed':random_seed,
            'n_predict_parts':n_predict_parts,
            'n_test_to_sample':n_test_to_sample,
        }

        ncaa.run_parallel(train_fpath=train_fpath, 
                          test_fpath=test_fpath, 
                          classifier_filepath=classifier_filepath, 
                          pars=parallel_pars,
                          do_debug_single_thread=False)
