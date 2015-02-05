#!/usr/bin/env python
""" Tools which enable feature generation
for sources in the StarVars project.

*** TODO parse the ASAS file into a string for below
*** parse raw ASAS ts files (as string):
              tutor_database_project_insert.py:parse_asas_ts_data_str(ts_str)
*** The aperture is chosen and the cooresp timeseries is decided in:
              tutor_database_project_insert.py:filter_best_ts_aperture()
*** TODO insert the resulting v_array int CSV parsing & freature generation code
*** TODO store the resulting features in an arff file / CSV format?

NOTE: I resolved library / python package dependencies by doing:
  1) editing my ~/.bashrc.ext:

export PATH=/global/homes/d/dstarr/local/bin:${PATH}
export TCP_DIR=/global/homes/d/dstarr/src/TCP/

  2) loading some modules (on NERSC computers):
module load python/2.7.1 numpy/1.6.1 scipy/0.10.1 ipython/0.12.1 R/2.12.1 mysql/5.1.63
   (on CITRIS-33node cluster): module load intel/11.1.072 gcc

"""
from __future__ import print_function
from __future__ import absolute_import
import sys, os
try:
    from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
except:
    pass
class IPython_Parallel_Processing:
    """
    This runs feature generation on the CITRIS/IBM 33-machine cluster which 
    has IPython-Parallel v0.10 set up for parallelization.

    This is not intended to be run on NERSC / carver.nersc.gov.

    Adapted from arff_generation_master.py::master_ipython_arff_generation()

    """
    def __init__(self, pars={}):
        self.pars = pars

    def main(self):
        """
    Adapted from arff_generation_master.py::master_ipython_arff_generation()
    This is intended to be used on pre IPython v0.12

        """
        import time
        import datetime
        import os
        try:
            from IPython.kernel import client
        except:
            pass

        mec = client.MultiEngineClient()
        mec.reset(targets=mec.get_ids()) # Reset the namespaces of all engines
        tc = client.TaskClient()

        mec_exec_str = """
import sys, os
import copy
import io
import cPickle
import gzip
import matplotlib
matplotlib.use('agg')
sys.path.append(os.path.abspath('/global/home/users/dstarr/src/TCP/Software/ingest_tools'))
sys.path.append(os.path.abspath('/global/home/users/dstarr/src/TCP/Software/citris33'))
from starvars_feature_generation import StarVars_ASAS_Feature_Generation
sv_asas = StarVars_ASAS_Feature_Generation(pars=%s)
""" % (str(self.pars))

        print('before mec()')
        engine_ids = mec.get_ids()
        pending_result_dict = {}
        for engine_id in engine_ids:
            pending_result_dict[engine_id] = mec.execute(mec_exec_str, targets=[engine_id], block=False)
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
                mec.clear_pending_results()
                pending_result_dict = {}
                mec.reset(targets=still_pending_dict.keys())
                for engine_id in still_pending_dict.keys():
                    pending_result_dict[engine_id] = mec.execute(mec_exec_str, targets=[engine_id], block=False)
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


        task_id_list = []
        result_arff_list = []

        ### Get a list of all ACVS source files
        acvs_fnames = os.listdir("%s/" % (self.pars['acvs_raw_dirpath']))
        acvs_fpaths = []
        for fpath in acvs_fnames:
            acvs_fpaths.append("%s/%s" % (self.pars['acvs_raw_dirpath'],
                                          fpath))
        if 1:
            ### This is used to generate the arff header strings by generating features 
            ###  for 1 source.  It is also a good single thread test that the task code works.

            sublist = acvs_fpaths[:1]

            import sys, os
            import copy 
            import io
            import matplotlib
            matplotlib.use('agg')
            sys.path.append(os.path.abspath('/global/home/users/dstarr/src/TCP/Software/ingest_tools'))
            sys.path.append(os.path.abspath('/global/home/users/dstarr/src/TCP/Software/citris33'))
            from .starvars_feature_generation import StarVars_ASAS_Feature_Generation
            sv_asas = StarVars_ASAS_Feature_Generation(pars=self.pars) # # # IMPORTANT
            tmp_stdout = sys.stdout
            sys.stdout = open(os.devnull, 'w')
            arff_output_fp = io.StringIO()
            sv_asas.generate_arff_using_asasdat(data_fpaths=sublist,
                                                include_arff_header=True,
                                                arff_output_fp=arff_output_fp)
            arff_rows_str = arff_output_fp.getvalue()
            header_lines = [a.strip() for a in arff_rows_str.split('\n')]
            out_dict = {'arff_rows_str':arff_rows_str}
            sys.stdout.close()
            sys.stdout = tmp_stdout

        n_src_per_task = 10 # 10 # NOTE: is generating PSD(freq) plots within lightcurve.py, should use n_src_per_task = 1, and all tasks should finish.# for ALL_TUTOR, =1 ipcontroller uses 99% memory, so maybe =3? (NOTE: cant do =10 since some TUTOR sources fail)

        imin_list = range(0, len(acvs_fpaths), n_src_per_task)

        for i_min in imin_list:
            sublist = acvs_fpaths[i_min: i_min + n_src_per_task]
            ### 20110106: This doesn't seem to solve the ipcontroller memory error, but works:
            tc_exec_str = """
tmp_stdout = sys.stdout
sys.stdout = open(os.devnull, 'w')
os.system('touch /global/home/groups/dstarr/debug_started/start')
arff_output_fp = io.StringIO()
out_dict = {}
sv_asas.generate_arff_using_asasdat(data_fpaths=sublist,
                                    include_arff_header=False,
                                    arff_output_fp=arff_output_fp,
                                    skip_class=False)
arff_rows_str = arff_output_fp.getvalue()
out_dict = {'arff_rows_str':arff_rows_str}
os.system('touch /global/home/groups/dstarr/debug/finish')
sys.stdout.close()
sys.stdout = tmp_stdout

            """
            taskid = tc.run(client.StringTask(tc_exec_str,
                                          push={'sublist':sublist},
                                          pull='out_dict', 
                                          retries=3))
            task_id_list.append(taskid)

        dtime_pending_1 = None
        while ((tc.queue_status()['scheduled'] > 0) or
               (tc.queue_status()['pending'] > 0)):
            tasks_to_pop = []
            for task_id in task_id_list:
                temp = tc.get_task_result(task_id, block=False)
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
                    result_arff_list.extend([a.strip() for a in results['arff_rows_str'].split('\n')])
            for task_id in tasks_to_pop:
                task_id_list.remove(task_id)

            if ((tc.queue_status()['scheduled'] == 0) and 
                (tc.queue_status()['pending'] <= 7)):
               if dtime_pending_1 is None:
                   dtime_pending_1 = datetime.datetime.now()
               else:
                   now = datetime.datetime.now()
                   if ((now - dtime_pending_1) >= datetime.timedelta(seconds=1200)):
                       print("dtime_pending=1 timeout break!")
                       break
            print(tc.queue_status())
            print('Sleep... 60 in starvars_feature_generation:IPython_Parallel_Processing.main()', datetime.datetime.utcnow())
            time.sleep(60)
        # IN CASE THERE are still tasks which have not been pulled/retrieved:
        for task_id in task_id_list:
            temp = tc.get_task_result(task_id, block=False)
            if temp is None:
                continue
            temp2 = temp.results
            if temp2 is None:
                continue
            results = temp2.get('out_dict',None)
            if results is None:
                continue #skip some kind of NULL result
            if len(results) > 0:
                result_arff_list.extend([a.strip() for a in results['arff_rows_str'].split('\n')])
        ####
        arff_rows = []
        for row in result_arff_list:
            if len(row) == 0:
                continue
            elif row[:5] == '@data':
                continue
            elif row[:16] == '@ATTRIBUTE class':
                continue
            else:
                arff_rows.append(row)

        print(tc.queue_status())
        return header_lines[:-2] + arff_rows


    def main_ipython13(self):
        """
        Adapted from arff_generation_master.py::master_ipython_arff_generation()
        Adapted from main() # which was intended to be used on pre IPython v0.12
        """
        import time
        import datetime
        import os
        try:
            from IPython.parallel import Client
        except:
            pass

        os.system("scp %s:%s %s" % (self.pars['ipython']['remote_hostname'],
                                    self.pars['ipython']['remote_client_json_fpath'],
                                    self.pars['ipython']['local_client_json_fpath']))

        rc = Client(self.pars['ipython']['local_client_json_fpath'],
                    sshserver=self.pars['ipython']['remote_hostname'])
        print('rc.ids:', rc.ids)

        ##### Multi-engine:
        dview = rc[:] # Direct View Object:  use all engines

        while len(dview.queue_status().keys()) < (self.pars['ipython']['n_engines'] + 1):
            print("%s Waiting for (%d) more engines to start." % (str(datetime.datetime.now()), (self.pars['ipython']['n_engines'] + 1) - len(dview.queue_status().keys())))
            time.sleep(1)
            dview = rc[:]
        dview.block=True  # all subsequent dview/multi-engine method calls will block.

        dview.clear()
        with dview.sync_imports(quiet=False):
            import sys
            import os

        dview.execute("""sys.path.append(os.path.abspath('/home/dstarr/src/TCP/Software/ingest_tools'))
sys.path.append(os.path.abspath('/home/dstarr/src/TCP/Software/citris33'))
        """)

        ### Get a list of all ACVS source files
        acvs_fnames = os.listdir("%s/" % (self.pars['task']['acvs_raw_dirpath']))
        acvs_fpaths = []
        for fpath in acvs_fnames:
            acvs_fpaths.append("%s/%s" % (self.pars['task']['acvs_raw_dirpath'],
                                          fpath))
        if 1:
            ### This is used to generate the arff header strings by generating features 
            ###  for 1 source.  It is also a good single thread test that the task code works.
            sublist = acvs_fpaths[:1]
            import sys, os
            import copy
            import io
            import cPickle
            import gzip
            import matplotlib
            matplotlib.use('agg')
            sys.path.append(os.path.abspath('/home/dstarr/src/TCP/Software/ingest_tools'))
            sys.path.append(os.path.abspath('/home/dstarr/src/TCP/Software/citris33'))
            from .starvars_feature_generation import StarVars_ASAS_Feature_Generation

            sv_asas = StarVars_ASAS_Feature_Generation(pars=self.pars['task']) # # # IMPORTANT
            
            #tmp_stdout = sys.stdout
            #sys.stdout = open(os.devnull, 'w')
            arff_output_fp = io.StringIO()
            sv_asas.generate_arff_using_asasdat(data_fpaths=sublist,
                                                include_arff_header=True,
                                                arff_output_fp=arff_output_fp)
            arff_rows_str = arff_output_fp.getvalue()
            #import pdb; pdb.set_trace()
            #print
            header_lines = [a.strip() for a in arff_rows_str.split('\n')]
            out_dict = {'arff_rows_str':arff_rows_str}
            #sys.stdout.close()
            #sys.stdout = tmp_stdout

        n_src_per_task = 5 # 10 # NOTE: is generating PSD(freq) plots within lightcurve.py, should use n_src_per_task = 1, and all tasks should finish.# for ALL_TUTOR, =1 ipcontroller uses 99% memory, so maybe =3? (NOTE: cant do =10 since some TUTOR sources fail)


        ### Create a load-balanced view for load-balanced execution:
        lview = rc.load_balanced_view() # default load-balanced view
        lview.block = False #True

        ### TODO: in previous versions of the code, I spit stdout to devnull, to reduce memory
        ###  - TODO: should test to see if this is an issue in memory usage
        @lview.parallel()
        def do_stuff(in_tup):
            (sublist, pars) = in_tup
            import io
            arff_output_fp = io.StringIO()
            out_dict = {}
            from .get_colors_for_tutor_sources import Parse_Nomad_Colors_List
            from .starvars_feature_generation import StarVars_ASAS_Feature_Generation #path already defined
            sv_asas = StarVars_ASAS_Feature_Generation(pars=pars)
            sv_asas.generate_arff_using_asasdat(data_fpaths=sublist,
                                                include_arff_header=False,
                                                arff_output_fp=arff_output_fp,
                                                skip_class=False)
            arff_rows_str = arff_output_fp.getvalue()
            out_dict = {'arff_rows_str':arff_rows_str}
            return out_dict

        #import pdb; pdb.set_trace()
        #print
        imin_list = range(0, len(acvs_fpaths), n_src_per_task)#[:pars['ipython']['n_engines']]#[:80]

        ### this is done in parallel:
        out = do_stuff.map([(acvs_fpaths[i_min: i_min + n_src_per_task],
                             self.pars['task']) for i_min in imin_list])

        while not out.ready():
            print("  %s T_elapsed=%0.1f  PercProgress=%0.2f" % (str(datetime.datetime.now()),out.elapsed,100. * out.progress/len(out)))
            time.sleep(5)

        print('wall_time:', out.wall_time)
        print('Factor speedup:', out.serial_time / out.wall_time)
        result_arff_list = []
        for result in out:
            result_arff_list.extend([a.strip() for a in result['arff_rows_str'].split('\n')])
        ####
        arff_rows = []
        for row in result_arff_list:
            if len(row) == 0:
                continue
            elif row[:5] == '@data':
                continue
            elif row[:16] == '@ATTRIBUTE class':
                continue
            else:
                arff_rows.append(row)
        return header_lines[:-2] + arff_rows



class StarVars_ASAS_Feature_Generation:
    """
    """
    def __init__(self, pars={}):
        self.head_str = """<?xml version="1.0"?>
<VOSOURCE version="0.04">
	<COOSYS ID="J2000" equinox="J2000." epoch="J2000." system="eq_FK5"/>
  <history>
    <created datetime="2009-12-02 20:56:18.880560" codebase="db_importer.pyc" codebase_version="9-Aug-2007"/>
  </history>
  <ID>6930531</ID>
  <WhereWhen>
    <Description>Best positional information of the source</Description>
    <Position2D unit="deg">
      <Value2>
        <c1>323.47114731</c1>
        <c2>-0.79916734036</c2>
      </Value2>
      <Error2>
        <c1>0.000277777777778</c1>
        <c2>0.000277777777778</c2>
      </Error2>
    </Position2D>
  </WhereWhen>
  <VOTimeseries version="0.04">
    <TIMESYS>
			<TimeType ucd="frame.time.system?">MJD</TimeType> 
			<TimeZero ucd="frame.time.zero">0.0 </TimeZero>
			<TimeSystem ucd="frame.time.scale">UTC</TimeSystem> 
			<TimeRefPos ucd="pos;frame.time">TOPOCENTER</TimeRefPos>
		</TIMESYS>

    <Resource name="db photometry">
        <TABLE name="v">
          <FIELD name="t" ID="col1" system="TIMESYS" datatype="float" unit="day"/>
          <FIELD name="m" ID="col2" ucd="phot.mag;em.opt.v" datatype="float" unit="mag"/>
          <FIELD name="m_err" ID="col3" ucd="stat.error;phot.mag;em.opt.v" datatype="float" unit="mag"/>
          <DATA>
            <TABLEDATA>
"""

        self.tail_str = """              </TABLEDATA>
            </DATA>
          </TABLE>
        </Resource>
      </VOTimeseries>
</VOSOURCE>"""

        self.pars=pars


    def write_limitmags_into_pkl(self, frame_limitmags):
        """ This parses the adt.frame_limitmags dictionary which is contained
        in a Pickle file and which was originally retrieved from
        mysql and from adt.retrieve_fullcat_frame_limitmags()
        """
        import cPickle
        import gzip
        ### This is just for writing the pickle file:
        fp = gzip.open(self.pars['limitmags_pkl_gz_fpath'],'w')
        cPickle.dump(frame_limitmags, fp, 1) # 1 means binary pkl used
        fp.close()


    def retrieve_limitmags_from_pkl(self):
        """ This parses the adt.frame_limitmags dictionary which is contained
        in a Pickle file and which was originally retrieved from
        mysql and from adt.retrieve_fullcat_frame_limitmags()
        """
        import cPickle
        import gzip
        fp = gzip.open(self.pars['limitmags_pkl_gz_fpath'],'rb')
        frame_limitmags = cPickle.load(fp)
        fp.close()
        return frame_limitmags


    def form_xml_string(self, mag_data_dict):
        """ Take timeseries dict data and place into VOSource XML format, 
        which TCP feature generation code expects.

        Adapted from: TCP/Software/feature_extract/format_csv_getfeats.py
        """
        data_str_list = []

        for i, t in enumerate(mag_data_dict['t']):
            m = mag_data_dict['m'][i]
            m_err = mag_data_dict['merr'][i]
            data_str = '              <TR row="%d"><TD>%lf</TD><TD>%lf</TD><TD>%lf</TD></TR>' % \
                (i, t, m, m_err)
            data_str_list.append(data_str)
            
        all_data_str = '\n'.join(data_str_list)
        out_xml = self.head_str + all_data_str + self.tail_str
        return out_xml


    def example_dat_parse(self):
        """
        """
        from . import tutor_database_project_insert
        adt = tutor_database_project_insert.ASAS_Data_Tools(pars=pars)
        if 0:
            ### requires mysql connection to TUTOR:
            adt.retrieve_fullcat_frame_limitmags() 
            self.write_limitmags_into_pkl(adt.frame_limitmags)

        ### This is done when we don't have a connection to the mysql database.
        adt.frame_limitmags = self.retrieve_limitmags_from_pkl()

        dat_fpath = '/global/homes/d/dstarr/scratch/082954-6245.6.dat'
        ts_str = open(dat_fpath).read()
        source_intermed_dict = adt.parse_asas_ts_data_str(ts_str)
        mag_data_dict = adt.filter_best_ts_aperture(source_intermed_dict)
        xml_str = self.form_xml_string(mag_data_dict)

        ### TODO Generate the features for this xml string

        import pdb; pdb.set_trace()
        print()


    def generate_arff_using_asasdat(self, data_fpaths=[], include_arff_header=False, arff_output_fp=None, skip_class=False):
        """ Given a list of ASAS data file filepaths, for each source/file:
        - choose the optimal aperture, depending upon median magnitude,
        - exclude bad/flagged epochs
        - generate features from timeseries (placing in intermediate XML-string format)
        - collect resulting features for all given sources, and place in ARFF style file
              which will later be read by ML training/classification code.
              
        Partially adapted from: TCP/Software/citris33/arff_generation_master_using_generic_ts_data.py:get_dat_arffstrs()
        """
        from .get_colors_for_tutor_sources import Parse_Nomad_Colors_List
        from . import tutor_database_project_insert
        adt = tutor_database_project_insert.ASAS_Data_Tools(pars=self.pars)
        adt.frame_limitmags = self.retrieve_limitmags_from_pkl()

        sys.path.append(os.environ.get('TCP_DIR') + '/Software/feature_extract/MLData')
        #sys.path.append(os.path.abspath(os.environ.get("TCP_DIR") + '/Software/feature_extract/Code/extractors'))
        #print os.environ.get("TCP_DIR")
        import arffify

        sys.path.append(os.path.abspath(os.environ.get("TCP_DIR") + \
                      'Software/feature_extract/Code'))
        import db_importer
        from data_cleaning import sigmaclip_sdict_ts
        sys.path.append(os.path.abspath(os.environ.get("TCP_DIR") + \
                      'Software/feature_extract'))
        from Code import generators_importers

        master_list = []
        master_features_dict = {}
        all_class_list = []
        master_classes_dict = {}

        for dat_fpath in data_fpaths:
            ### This truncates at file extension '.'
            #new_srcid = "'" + dat_fpath[dat_fpath.rfind('/')+1:dat_fpath.rfind('.')] + "'"
            #### This is for ACVS files, which have '.' in the source-name:
            new_srcid = "'" + dat_fpath[dat_fpath.rfind('/')+1:] + "'"
            ts_str = open(dat_fpath).read()
            source_intermed_dict = adt.parse_asas_ts_data_str(ts_str)
            mag_data_dict = adt.filter_best_ts_aperture(source_intermed_dict)
            try:
                xml_str = self.form_xml_string(mag_data_dict)
            except:
                print("FAILED:form_xml_string()", dat_fpath)
                continue # skip this source
            #from get_colors_for_tutor_sources import Parse_Nomad_Colors_List
            #ParseNomadColorsList = Parse_Nomad_Colors_List(fpath=os.path.abspath(os.environ.get("TCP_DIR") + '/Data/best_nomad_src_list'))
            ParseNomadColorsList = Parse_Nomad_Colors_List(fpath='/home/dstarr/src/TCP/Data/best_nomad_src_for_asas_kepler')

            ### Generate the features:
            signals_list = []
            gen = generators_importers.from_xml(signals_list)
            if 1:
                #import pdb; pdb.set_trace()
                #print
                new_xml_str = ParseNomadColorsList.get_colors_for_srcid(xml_str=xml_str, srcid=new_srcid)

            gen.generate(xml_handle=new_xml_str)
            gen.sig.add_features_to_xml_string(signals_list)                
            gen.sig.x_sdict['src_id'] = new_srcid
            dbi_src = db_importer.Source(make_dict_if_given_xml=False)
            dbi_src.source_dict_to_xml(gen.sig.x_sdict)

            xml_fpath = dbi_src.xml_string

            a = arffify.Maker(search=[], skip_class=skip_class, local_xmls=True, convert_class_abrvs_to_names=False, flag_retrieve_class_abrvs_from_TUTOR=False, dorun=False)
            out_dict = a.generate_arff_line_for_vosourcexml(num=new_srcid, xml_fpath=xml_fpath)

            master_list.append(out_dict)
            all_class_list.append(out_dict['class'])
            master_classes_dict[out_dict['class']] = 0
            for feat_tup in out_dict['features']:
                master_features_dict[feat_tup] = 0 # just make sure there is this key in the dict.  0 is filler


        master_features = master_features_dict.keys()
        master_classes = master_classes_dict.keys()
        a = arffify.Maker(search=[], skip_class=skip_class, local_xmls=True, 
                          convert_class_abrvs_to_names=False,
                          flag_retrieve_class_abrvs_from_TUTOR=False,
                          dorun=False, add_srcid_to_arff=True)
        a.master_features = master_features
        a.all_class_list = all_class_list
        a.master_classes = master_classes
        a.master_list = master_list


        a.write_arff(outfile=arff_output_fp, \
                     remove_sparse_classes=True, \
                     n_sources_needed_for_class_inclusion=1,
                     include_header=include_arff_header,
                     use_str_srcid=True)#, classes_arff_str='', remove_sparse_classes=False)



if __name__ == '__main__':

    ### Carver (IPytohon v0.12.1
    #'limitmags_pkl_gz_fpath':'/project/projectdirs/m1583/ASAS_scratch/asas_limitmags.pkl.gz',

    ### Citris33 (Ipython v0.10):
    #pars = {'out_arff_fpath':'/global/home/users/dstarr/500GB/acvs_50k_raw/combined_acvs.arff',
    #        'acvs_raw_dirpath':'/global/home/users/dstarr/500GB/acvs_50k_raw/timeseries',
    #        'limitmags_pkl_gz_fpath':'/global/home/users/dstarr/500GB/acvs_50k_raw/asas_limitmags.pkl.gz'}
    
    # Anathem (IPython v0.13.1dev):
    pars = { \
        'out_arff_fpath':'/home/dstarr/Data/starvars/combined_acvs.arff',
        'task':{'acvs_raw_dirpath':'/home/dstarr/Data/kepler_asas_947/asas_v_data', #'/Data/dstarr/Data/asas_ACVS_50k_data/timeseries',
                'limitmags_pkl_gz_fpath':'/home/dstarr/scratch/asas_limitmags.pkl.gz'},
        'ipython':{'remote_client_json_fpath':'/home/dstarr/.ipython/profile_default/security/ipcontroller-client.json',
                   'local_client_json_fpath':'/tmp/ipcontroller-client.json',
                   'remote_hostname':'anathem',
                   'n_engines':24}, # required in order to ensure all engines are available.
        }


    data_fpaths = ['/project/projectdirs/m1583/ASAS_scratch/082954-6245.6.dat',
                   '/project/projectdirs/m1583/ASAS_scratch/183007-1351.0.dat']
    if 0:
        ### Example: generate arff feature string, do not write to file:
        import io
        arff_output_fp = io.StringIO()
        sv_asas = StarVars_ASAS_Feature_Generation(pars=pars)
        #sv_asas.example_dat_parse()
        sv_asas.generate_arff_using_asasdat(data_fpaths=data_fpaths,
                                            include_arff_header=False,
                                            arff_output_fp=arff_output_fp)

        arff_rows_str = arff_output_fp.getvalue()
        print(arff_rows_str)

    if 0:
        ### Example: generate arff feature string, write to some file:
        arff_output_fp = open('out.arff', 'w')
        sv_asas = StarVars_ASAS_Feature_Generation(pars=pars)
        sv_asas.generate_arff_using_asasdat(data_fpaths=data_fpaths,
                                            include_arff_header=False,
                                            arff_output_fp=arff_output_fp)
        arff_output_fp.close()

    if 1:
        ### This does feature generation for ASAS 50000 ACVS using Ipython Parallel.
        ipp = IPython_Parallel_Processing(pars=pars)
        #combined_arff_rows = ipp.main() # For Ipython v0.10 / citris33
        combined_arff_rows = ipp.main_ipython13()
        fp = open(pars['out_arff_fpath'],'w')
        for row in combined_arff_rows:
            fp.write(row + '\n')
        fp.close()
        print("Wrote:", pars['out_arff_fpath'])
        import pdb; pdb.set_trace()
        print()
