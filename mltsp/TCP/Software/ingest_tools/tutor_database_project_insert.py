#!/usr/bin/env python
""" A script which initially is intended to duplicate a project in the tutor DB
(with some source exclusions), and then add some additional sources.

NOTE: the data will mostely com from tutor-database rows, although some ids
      will need to be auto-incremented:
            observations.observation_id
            projects.project_id


+-----------------+
access            |                                                                 count(*)=52
authors           | (AUTO author_id)
class_aliases     | NONE
class_ancestors   | (class_id, class_id_ancestor, cancestor_path)                   count(*)=1167
class_tags        |                                                                 count(*)=66
classes           | (AUTO class_id, class_id_parent)                                count(*)=276
filters           | 
instruments       | (AUTO instrument_id)
obs_data          | (observation_id, obsdata_time)     max(observation_id)=420977   count(*)=27496237
observations      | (AUTO observation_id, source_id, instrument_id, filter_id)      count(*)=383830
project_authors   | 
project_classes   | (AUTO pclass_id, project_id)                                    count(*)=311
projects          | (AUTO project_id)   max(project_id)=122
sclass_groups     | NONE
section_functions | N/A
sections          | N/A                                                             count(*)=4
source_classes    | OBSOLETE? (source_id, scgroup_id, class_id)                     count(*)=188
source_tags       |                                                                 count(*)=206
sources           | (AUTO source_id, project_id, class_id, pclass_id)      max(source_id)=163323
surveys           | (AUTO survey_id)                                                count(*)=4
tags              | 
telescopes        | 
users             | 
+-----------------+


NOTE: for ASAS ACVS import, I found that some pclasses did not get correctly matched with TUTOR existing classes.  Here are some update strings to correct this:

##d   ED    class_id= 281 :
UPDATE sources SET class_id=281 where pclass_id=401 and project_id=126;
UPDATE project_classes SET class_id=281 where pclass_id=401 and project_id=126;

##ds  DSCT  class_id= 211 :
UPDATE sources SET class_id=211 where pclass_id=399 and project_id=126;
UPDATE project_classes SET class_id=211 where pclass_id=399 and project_id=126;

##sd  ESD   class_id= 282 :
UPDATE sources SET class_id=282 where pclass_id=402 and project_id=126;
UPDATE project_classes SET class_id=282 where pclass_id=402 and project_id=126;

"""
from __future__ import print_function
import os, sys
import MySQLdb
import cPickle
import pprint
import glob
import gzip
import numpy
sys.path.append(os.path.abspath(os.environ.get("TCP_DIR") + "Algorithms"))
import simbad_id_lookup

def invoke_pdb(type, value, tb):
    """ Cool feature: on crash, the debugger is invoked in the last
    state of the program.  To Use, call in __main__: sys.excepthook =
    invoke_pdb
    """
    import traceback, pdb
    traceback.print_exception(type, value, tb)
    print()
    pdb.pm()


def calc_variance(x, n, mean, variance):
    """ Online variance calculation algorithm.
    Adapted from:   stackoverflow.com/questions/3903538
    """
    m2 = variance * n
    n += 1
    delta = x - mean
    mean += delta/float(n)
    m2 += delta*(x - mean)
    variance = m2 / float(n)
    return (n,
            mean,
            variance)


class TutorDb():
    def __init__(self, pars={}):
        self.pars = pars
        self.db = MySQLdb.connect(host=self.pars['tcptutor_hostname'],
                                  user=self.pars['tcptutor_username'],
                                  db=self.pars['tcptutor_database'],
                                  port=self.pars['tcptutor_port'],
                                  passwd=self.pars['tcptutor_password'])
        self.cursor = self.db.cursor()

        self.query_filter_lookup()


    def query_filter_lookup(self):
        """ Query TUTOR DB for filter_ids for each filter_name
        """
        select_str = "SELECT filter_name, filter_id FROM filters"

        self.cursor.execute(select_str)
        results = self.cursor.fetchall()

        self.filter_name_to_id = {}
        self.filter_id_to_name = {}
        for row in results:
            (filter_name, filter_id) = row
            self.filter_name_to_id[filter_name] = filter_id
            self.filter_id_to_name[filter_id] = filter_name


    def query_sourcename_sourceid_lookup(self, project_id=122):
        """
        # Select sources.source_id, sources.source_name  which will be used for insert into observations
        """
        select_str = "SELECT source_id, source_name FROM sources WHERE project_id=%d" % \
                             (project_id)
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()

        sourceid_lookup = {}
        for row in results:
            (source_id, source_name) = row
            sourceid_lookup[source_name.strip()] = int(source_id)

        return sourceid_lookup

        
    def update_with_sourceids(self, sourceid_lookup={}, source_data={}):
        """ Match sourceids to source names.  Store in source_data dict.
        """
        for source_dict in source_data.values():
            assert(source_dict['source_name'] in sourceid_lookup)
            source_dict['source_id'] = sourceid_lookup[source_dict['source_name']]


    def insert_into_observations_table(self, debug=True, source_data={},
                                       instrument_id = 0,
                                       user_id = 3,
                                       observation_ucd = 'phot.mag',
                                       observation_units = 'mag',
                                       observation_time_scale = 1,
                                       observation_description = 'c',
                                       observation_bright_limit_low = None,
                                       observation_bright_limit_high = None):
        """  Using srcid, insert the single filter/band source into table.
        A unique observation-id is generated by mysql.
        """
        
        sources_insert_list = ["INSERT INTO observations (source_id, instrument_id , filter_id , user_id , observation_ucd , observation_units , observation_time_format , observation_time_scale , observation_description , observation_bright_limit_low , observation_bright_limit_high , observation_start , observation_end) VALUES "]
        n_src_per_insert = 1000
        src_count = 0

        observation_time_format = self.pars.get('observation_time_format','')

        for source_dict in source_data.values():
            source_id = source_dict['source_id']
            for filt_name, filt_dict in source_dict['ts_data'].iteritems():
                assert(filt_name in self.filter_name_to_id)
                filter_id = self.filter_name_to_id[filt_name]

                observation_start = min(filt_dict['t'])
                observation_end = max(filt_dict['t'])
                if len(observation_time_format) == 0:
                    if observation_start > 2000000:
                        observation_time_format = 'jd'
                    else:
                        observation_time_format = 'tjd' # This is used by project_id=122 (tjd)

                insert_tup = (source_id, instrument_id , filter_id , user_id , observation_ucd , observation_units , observation_time_format , observation_time_scale , observation_description , observation_bright_limit_low , observation_bright_limit_high , observation_start , observation_end)

                sources_insert_list.append("""(%d, %d, %d, %d, '%s', '%s', '%s', %d, '%s', '%s', '%s', %lf, %lf), """ %  insert_tup)
                src_count += 1
                if src_count > n_src_per_insert:
                    sources_insert_str = ''.join(sources_insert_list)[:-2]
                    if not debug:
                        print('INSERTing: ...')
                        self.cursor.execute(sources_insert_str)
                        sources_insert_list = ["INSERT INTO observations (source_id, instrument_id , filter_id , user_id , observation_ucd , observation_units , observation_time_format , observation_time_scale , observation_description , observation_bright_limit_low , observation_bright_limit_high , observation_start , observation_end) VALUES "]
                        
        sources_insert_str = ''.join(sources_insert_list)[:-2]

        if len(sources_insert_list) > 1:
            if debug:
                #print sources_insert_str
                for elem in sources_insert_list:
                    print(elem)
                #print sources_insert_list[0]
                #print sources_insert_list[1]
                #print sources_insert_list[2]
                #print sources_insert_list[3]
            else:
                print(sources_insert_list[0])
                print(sources_insert_list[1])
                #print sources_insert_list[2]
                #print sources_insert_list[3]
                print('INSERTing: ...')
                self.cursor.execute(sources_insert_str)


    def update_observations_table(self, debug=True, source_data={},
                                       instrument_id = 0,
                                       user_id = 3,
                                       observation_ucd = 'phot.mag',
                                       observation_units = 'mag',
                                       observation_time_scale = 1,
                                       observation_description = 'c',
                                       observation_bright_limit_low = None,
                                       observation_bright_limit_high = None):
        """  Using srcid, insert the single filter/band source into table.
        A unique observation-id is generated by mysql.
        """
        
        sources_insert_list = ["INSERT INTO observations (observation_id, source_id, instrument_id , filter_id , user_id , observation_ucd , observation_units , observation_time_format , observation_time_scale , observation_description , observation_bright_limit_low , observation_bright_limit_high , observation_start , observation_end) VALUES "]
        n_src_per_insert = 1000
        src_count = 0

        observation_time_format = self.pars.get('observation_time_format','')

        for source_dict in source_data.values():
            source_id = source_dict['source_id']
            for filt_name, filt_dict in source_dict['ts_data'].iteritems():
                assert(filt_name in self.filter_name_to_id)
                filter_id = self.filter_name_to_id[filt_name]

                observation_start = min(filt_dict['t'])
                observation_end = max(filt_dict['t'])
                if len(observation_time_format) == 0:
                    if observation_start > 2000000:
                        observation_time_format = 'jd'
                    else:
                        observation_time_format = 'tjd' # This is used by project_id=122 (tjd)

                insert_tup = (source_dict['ts_data'][filt_name]['observation_id'], source_id, instrument_id , filter_id , user_id , observation_ucd , observation_units , observation_time_format , observation_time_scale , observation_description , observation_bright_limit_low , observation_bright_limit_high , observation_start , observation_end)

                sources_insert_list.append("""(%d, %d, %d, %d, %d, '%s', '%s', '%s', %d, '%s', '%s', '%s', %lf, %lf), """ %  insert_tup)
                src_count += 1
                if src_count > n_src_per_insert:
                    sources_insert_str = ''.join(sources_insert_list)[:-2]  + " ON DUPLICATE KEY UPDATE observation_start=VALUES(observation_start), observation_end=VALUES(observation_end)"
                    if not debug:
                        print('INSERTing: ...')
                        self.cursor.execute(sources_insert_str)
                        sources_insert_list = ["INSERT INTO observations (observation_id, source_id, instrument_id , filter_id , user_id , observation_ucd , observation_units , observation_time_format , observation_time_scale , observation_description , observation_bright_limit_low , observation_bright_limit_high , observation_start , observation_end) VALUES "]
                        
        sources_insert_str = ''.join(sources_insert_list)[:-2]  + " ON DUPLICATE KEY UPDATE observation_start=VALUES(observation_start), observation_end=VALUES(observation_end)"

        if len(sources_insert_list) > 1:
            if debug:
                #print sources_insert_str
                for elem in sources_insert_list:
                    print(elem)
                #print sources_insert_list[0]
                #print sources_insert_list[1]
                #print sources_insert_list[2]
                #print sources_insert_list[3]
            else:
                print(sources_insert_list[0])
                print(sources_insert_list[1])
                #print sources_insert_list[2]
                #print sources_insert_list[3]
                print('INSERTing: ...')
                self.cursor.execute(sources_insert_str)


    def insert_into_obsdata_table(self, debug=True, source_data={}, delete_entries_first=False, insert_limits=False):
        """  Using observation_id, insert m,t,merr info into table.
        """
        obsdata_limit = False
        obsdata_limit_sigma = 0
        for source_dict in source_data.values():
            source_id = source_dict['source_id']
            sources_insert_list = ["INSERT IGNORE INTO obs_data (observation_id, obsdata_time, obsdata_val, obsdata_err, obsdata_limit, obsdata_limit_sigma) VALUES "]

            for filt_name, filt_dict in source_dict['ts_data'].iteritems():
                observation_id = filt_dict['observation_id']

                if (not debug) and delete_entries_first:
                    del_str = "DELETE FROM obs_data WHERE observation_id=%d" % (observation_id)
                    self.cursor.execute(del_str)

                for i in xrange(len(filt_dict['t'])):
                    obsdata_time = filt_dict['t'][i]
                    if filt_dict['m'][i] <= self.pars.get('mag_null_value', -999999999):
                        #obsdata_val = "NULL"
                        continue  # we skip observation epochs which have no data (and assuming no limiting mag info as well)
                    else:
                        obsdata_val = str(filt_dict['m'][i])
                    if 'merr' in filt_dict:
                        obsdata_err = filt_dict['merr'][i]
                    else:
                        obsdata_err = 0.
                    insert_tup = (observation_id, obsdata_time, obsdata_val, obsdata_err, obsdata_limit, obsdata_limit_sigma)
                    sources_insert_list.append("""(%d, %lf, %s, %lf, '%s', %d), """ %  insert_tup)

                if ((len(filt_dict.get('lim_t',[])) > 0) and (insert_limits)):
                    for i in xrange(len(filt_dict['lim_t'])):
                        insert_tup = (observation_id,
                                      filt_dict['lim_t'][i],
                                      filt_dict['lim_m'][i],
                                      filt_dict['lim_merr'][i])
                        # TODO: maybe have the obsdata_limit_sigma vary, depending on how many stddev the m_lim_err is
                        sources_insert_list.append("""(%d, %lf, %s, %lf, 'upper', 1), """ %  insert_tup)
                        

            sources_insert_str = ''.join(sources_insert_list)[:-2]
        
            if debug:
                pass
                #print sources_insert_str
                #print sources_insert_list[0]
                #print sources_insert_list[1]
                #print sources_insert_list[2]
                #print sources_insert_list[3]
            else:
                #print sources_insert_list[0]
                #print sources_insert_list[1]
                #print sources_insert_list[2]
                #print sources_insert_list[3]
                #print 'INSERTing: ...'
                self.cursor.execute(sources_insert_str)


    ### 20111206 no-limits backup:
    def insert_into_obsdata_table__nolimits(self, debug=True, source_data={}):
        """  Using observation_id, insert m,t,merr info into table.
        """
        obsdata_limit = False
        obsdata_limit_sigma = 0
        for source_dict in source_data.values():
            source_id = source_dict['source_id']
            sources_insert_list = ["INSERT IGNORE INTO obs_data (observation_id, obsdata_time, obsdata_val, obsdata_err, obsdata_limit, obsdata_limit_sigma) VALUES "]

            for filt_name, filt_dict in source_dict['ts_data'].iteritems():
                observation_id = filt_dict['observation_id']


                for i in xrange(len(filt_dict['t'])):
                    obsdata_time = filt_dict['t'][i]
                    if filt_dict['m'][i] <= self.pars.get('mag_null_value', -999999999):
                        #obsdata_val = "NULL"
                        continue  # we skip observation epochs which have no data (and assuming no limiting mag info as well)
                    else:
                        obsdata_val = str(filt_dict['m'][i])
                    if 'merr' in filt_dict:
                        obsdata_err = filt_dict['merr'][i]
                    else:
                        obsdata_err = 0.
                    insert_tup = (observation_id, obsdata_time, obsdata_val, obsdata_err, obsdata_limit, obsdata_limit_sigma)
                    sources_insert_list.append("""(%d, %lf, %s, %lf, '%s', %d), """ %  insert_tup)
            sources_insert_str = ''.join(sources_insert_list)[:-2]
        
            if debug:
                #print sources_insert_str
                print(sources_insert_list[0])
                print(sources_insert_list[1])
                print(sources_insert_list[2])
                print(sources_insert_list[3])
            else:
                print(sources_insert_list[0])
                print(sources_insert_list[1])
                print(sources_insert_list[2])
                print(sources_insert_list[3])
                print('INSERTing: ...')
                self.cursor.execute(sources_insert_str)



    def select_observation_ids(self, source_data={}):
        """
        select observation_id from observations table
        """
        for source_dict in source_data.values():
            source_id = source_dict['source_id']

            select_str = "SELECT observation_id, filter_id FROM observations WHERE source_id=%d" % \
                             (source_id)
            self.cursor.execute(select_str)
            results = self.cursor.fetchall()
            for row in results:
                (observation_id, filter_id) = row
                filter_name = self.filter_id_to_name[filter_id]
                source_dict['ts_data'][filter_name]['observation_id'] = observation_id
        

class TutorDebosscherProjectInsert(TutorDb):
    """ Methods needed to migrate, cull existing tutor / dotastro projects into new projects
    """
    def get_existing_project_table_info(self):
        """ Fill structures with general table info about existing project

        """
        proj_tables = {'update':{}, 'insert':{}}

        select_str = "SELECT max(project_id) FROM projects"
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        assert(results[0][0] + 1 == self.pars['new_proj_id'])

        ##### project_authors:
        select_str = "select project_id , author_id , project_author_lead from project_authors where project_id=%d" % (self.pars['old_proj_id'])
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()

        #proj_tables['update']['project_authors'] = "UPDATE project_authors SET project_id=%d , author_id=%d , project_author_lead='%s'" % (self.pars['new_proj_id'], results[0][1], results[0][2])
        proj_tables['insert']['project_authors'] = "INSERT INTO project_authors (project_id , author_id , project_author_lead) VALUES (%d, %d, '%s')" % (self.pars['new_proj_id'], results[0][1], results[0][2])


        ##### project_classes:
        select_str = """SELECT project_id , class_id , pclass_name , pclass_short_name , pclass_description
                        FROM project_classes
                        WHERE project_id=%d""" % (self.pars['old_proj_id'])
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        insert_list = ["INSERT INTO project_classes (project_id , class_id , pclass_name , pclass_short_name , pclass_description) VALUES "]
        for row in results:
            insert_list.append("""(%d, %d, "%s", "%s", "%s"), """ % \
                               (self.pars['new_proj_id'], row[1], row[2], row[3], row[4]))
        insert_str = ''.join(insert_list)[:-2]
        proj_tables['insert']['project_classes'] = insert_str


        ##### projects:
        select_str = """SELECT project_id , telescope_id , survey_id , user_id , project_title , project_url , project_data_url , project_abstract , project_status
                        FROM projects
                        WHERE project_id=%d""" % (self.pars['old_proj_id'])
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        proj_tables['insert']['projects'] = \
                    """INSERT INTO projects
                       (project_id , telescope_id , survey_id , user_id , project_title , project_url , project_data_url , project_abstract , project_status)
                       VALUES (%d, %d, %d, %d, "%s", "%s", "%s", "%s", "%s")""" % ( \
                        self.pars['new_proj_id'],
                        results[0][1],
                        results[0][2],
                        results[0][3],
                        "Debosscher 3",
                        results[0][5],
                        results[0][6],
                        results[0][7],
                        results[0][8])
        return proj_tables





    def get_josh_deboss_data_subset(self):
        """ Retrieve lists of HIPPARCOS object subset and reclassifications form
        (pkl?) output from debosscher_paper_tools.py

        TODO: Also include all OGLE source-ids (99.4%?) that should be included.
        TODO: Maybe exclude the science class Joey excludes


        """
        fp = open('/home/pteluser/scratch/debosscher_paper_tools__assocdict.pkl') # from debosscher_paper_tools.py
        deboss_class_assoc = cPickle.load(fp)
        fp.close()


        return deboss_class_assoc

    
    def insert_into_project_tables(self, debug=True, proj_tables={}):
        """ Create Project table row entries and fill all related tables / rows

        NOTE: disabling this should be fine if done once already
        
        """

        if debug:
            for insert_name, insert_str in proj_tables['insert'].iteritems():
                print(insert_str)
        else:
            print('INSERTing: ...')
            for insert_name, insert_str in proj_tables['insert'].iteritems():
                print(insert_str)
                self.cursor.execute(insert_str)



    def insert_known_sources_into_tables(self, debug=True, data_with_tutorids={},
                                         class_name_id_dict={}):
        """ Insert known sources from old project into tutor.sources TABLE.
        """
        sources_insert_list = ["INSERT INTO sources (project_id, pclass_id, user_id, class_id , source_pclass_confidence , source_class_confidence , source_oid     , source_name    , source_ra , source_ra_err , source_dec , source_dec_err , source_epoch , source_redshift_type , source_redshift , source_redshift_err , Source_Extinction_Type , Source_Extinction , Source_Extinction_Err) VALUES "]
        for hip_id, hip_dict in data_with_tutorids.iteritems():
            # TODO get rows and all info from sources table, then append to insert list
            select_str = """SELECT class_id , source_pclass_confidence , source_class_confidence , source_oid     , source_name    , source_ra , source_ra_err , source_dec , source_dec_err , source_epoch , source_redshift_type , source_redshift , source_redshift_err , Source_Extinction_Type , Source_Extinction , Source_Extinction_Err
                            FROM sources
                            WHERE project_id=%d AND source_id=%d """ % \
                            (self.pars['old_proj_id'], hip_dict['tutorid'])
            self.cursor.execute(select_str)
            results = self.cursor.fetchall()
            assert(len(results) == 1)
            row = results[0]

            if 'pclass_id' in hip_dict:
                pclass_id = hip_dict['pclass_id']
            else:
                pclass_id = class_name_id_dict[hip_dict['tcp_class']]['pclass_id']  # This dict is the new project
            if 'class_id' in hip_dict:
                class_id = hip_dict['class_id']
            else:
                class_id = class_name_id_dict[hip_dict['tcp_class']]['class_id']  # This dict is the new project
            ### NOTE: we do not use the SELECTed class_id::row[0]:
            insert_tup = (self.pars['new_proj_id'], pclass_id, self.pars['user_id'],
                  class_id, row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9],
                  row[10], row[11], row[12], row[13], row[14], row[15])
            sources_insert_list.append("""(%d, %d, %d, %d, %lf, %lf, "%s", "%s", %lf, %lf, %lf, %lf, "%s", "%s", %lf, %lf, "%s", %lf, %lf), """ %  insert_tup)

        sources_insert_str = ''.join(sources_insert_list)[:-2]
        if debug:
            #print sources_insert_list[0]
            #print sources_insert_list[1]
            #print sources_insert_list[2]
            #print sources_insert_list[3]
           for elem in sources_insert_list:
               print(elem)
        else:
            print(sources_insert_list[0])
            print(sources_insert_list[1])
            print(sources_insert_list[2])
            print(sources_insert_list[3])
            print('INSERTing: ...')
            self.cursor.execute(sources_insert_str)




    def insert_new_sources_into_tables(self, debug=True, data_without_tutorids={},
                                         class_name_id_dict={}):
        """ Insert new sources from old project into tutor.sources TABLE.

        TODO: Eventually we should add some additional source information (ra, dec), for each source.
         - ra,dec is a pretty neccissary data sanity check for later on (need to parse from Deboss files).

        """
        source_pclass_confidence = 0 # for all project_id=122 sources this is 0 and not 1
        source_class_confidence = 1
        source_ra_err = 0.0
        source_dec_err = 0.0
        source_epoch = 'j2000'
        source_redshift_type = None
        source_redshift = 0
        source_redshift_err = 0
        Source_Extinction_Type = None
        Source_Extinction = 0
        Source_Extinction_Err = 0

        sources_insert_list = ["INSERT INTO sources (project_id, pclass_id, user_id, class_id , source_pclass_confidence , source_class_confidence , source_oid     , source_name    , source_ra , source_ra_err , source_dec , source_dec_err , source_epoch , source_redshift_type , source_redshift , source_redshift_err , Source_Extinction_Type , Source_Extinction , Source_Extinction_Err) VALUES "]
        for hip_id, hip_dict in data_without_tutorids.iteritems():

            try:
                pclass_id = class_name_id_dict[hip_dict['tcp_class']]['pclass_id']  # This dict is the new project
            except:
                print('!!!', hip_id, hip_dict['tcp_class'])
                raise#continue
            class_id = class_name_id_dict[hip_dict['tcp_class']]['class_id']  # This dict is the new project

            source_name_str = hip_dict['xml'].replace('.xml','')
            insert_tup = (self.pars['new_proj_id'], pclass_id, self.pars['user_id'],
                          class_id, source_pclass_confidence, source_class_confidence, source_name_str,
                          source_name_str, hip_dict['ra'], source_ra_err, hip_dict['dec'], source_dec_err,
                          source_epoch, source_redshift_type , source_redshift , source_redshift_err ,
                          Source_Extinction_Type , Source_Extinction , Source_Extinction_Err)
            sources_insert_list.append("""(%d, %d, %d, %d, %lf, %lf, "%s", "%s", %lf, %lf, %lf, %lf, "%s", "%s", %lf, %lf, "%s", %lf, %lf), """ %  insert_tup)
        #import pdb; pdb.set_trace()
        sources_insert_str = ''.join(sources_insert_list)[:-2]
        if debug:
            #print sources_insert_str
            print(sources_insert_list[0])
            print(sources_insert_list[1])
            print(sources_insert_list[2])
            print(sources_insert_list[3])
        else:
            print(sources_insert_list[0])
            print(sources_insert_list[1])
            print(sources_insert_list[2])
            print(sources_insert_list[3])
            print('INSERTing: ...')
            self.cursor.execute(sources_insert_str)


    def parse_add_timeseries_data_from_files(self, debos_subset={}):
        """ Parse the timeseries data from Joey xml files

        NOTE: could parse this data from the original Debosscher data files, but
              Joey has already excluded flagged epochs, etc.
              
        NOTE: I believe Joey just generated these xmls using a non-xml conformal method,
              so my parsing method will not be an xml parser, to elliviate some potential headaches.

        """
        for hip_id, hip_dict  in debos_subset.iteritems():

            xml_fpath = "%s/%s" % (self.pars['joey_xml_dirpath'], hip_dict['xml'])
            lines = open(xml_fpath).readlines()

            hip_dict['t'] = []
            hip_dict['m'] = []
            hip_dict['merr'] = []
            parse_ts = False
            i = 0
            parse_file = True
            while parse_file:
                line = lines[i]
                if '<TABLEDATA>' in  line:
                    parse_ts = True
                elif '</TABLEDATA>' in line:
                    parse_ts = False
                    parse_file = False
                elif parse_ts:
                    # <TR row="64"><TD>8747.045540</TD><TD>8.201800</TD><TD>0.011000</TD></TR>
                    # <TR row="64"  TD>8747.045540</TD  TD>8.201800</TD  TD>0.011000</TD  /TR>
                    substr = line.split('><')
                    t_substr = substr[1]
                    t_str = t_substr[t_substr.find('>') + 1:t_substr.rfind('<')]
                    t_flt = float(t_str)
                    
                    m_substr = substr[2]
                    m_str = m_substr[m_substr.find('>') + 1:m_substr.rfind('<')]
                    m_flt = float(m_str)

                    merr_substr = substr[3]
                    merr_str = merr_substr[merr_substr.find('>') + 1:merr_substr.rfind('<')]
                    merr_flt = float(merr_str)
                    #print t_flt, m_flt, merr_flt, line.strip()
                    hip_dict['t'].append(t_flt)
                    hip_dict['m'].append(m_flt)
                    hip_dict['merr'].append(merr_flt)
                i += 1
            #pprint.pprint((hip_dict))
            #import pdb; pdb.set_trace()


    def select_sourceids__deboss(self, debos_subset={}):
        """
        # TODO: select sources.source_id, sources.source_name  which will be used for insert into observations
        #           - store results in dicts within debos_subset  (same refs as data_without_tutorids...)
        """
        #  'tutor_name'  'xml'
        select_str = "SELECT source_id, source_name FROM sources WHERE project_id=%d" % \
                             (self.pars['new_proj_id'])
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        for row in results:
            (source_id, source_name) = row
            if 'HIP' in source_name:
                hip_id = int(source_name.replace('HIP',''))
            elif 'HD' in source_name:
                html_str = simbad_id_lookup.query_html(src_name=source_name)
                hip_ids = simbad_id_lookup.parse_html_for_ids(html_str, instr_identifier='HIP')
                hip_id = int(hip_ids[0].replace('HIP',''))
            else:
                print("ERROR")
                raise
            debos_subset[hip_id]['new_srcid'] = source_id


    def select_sourceids_ogle(self, debos_subset={}):
        """
        # TODO: select sources.source_id, sources.source_name  which will be used for insert into observations
        #           - store results in dicts within debos_subset  (same refs as data_without_tutorids...)
        """
        #  'tutor_name'  'xml'

        srcname_srcid_dict = {}
        select_str = "SELECT source_id, source_name FROM sources WHERE project_id=%d" % \
                             (self.pars['new_proj_id'])
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        for row in results:
            (source_id, source_name) = row
            srcname_srcid_dict[source_name] = source_id


        for s_id, s_dict in debos_subset.iteritems():
            if s_dict['tutor_name'] in srcname_srcid_dict:
                s_dict['new_srcid'] = srcname_srcid_dict[s_dict['tutor_name']]
            else:
                print('MISSED:', s_id, s_dict)
                raise


    def insert_into_observations_table__deboss(self, debug=True, debos_subset={}):
        """  Using srcid, insert the single filter/band source into table.
        A unique observation-id is generated by mysql.
        """
        instrument_id = 0
        filter_id = 9 # This is used by project_id=122 (V)
        user_id = self.pars['user_id']
        observation_ucd = 'phot.mag'
        observation_units = 'mag'
        observation_time_scale = 1
        observation_description = 'c'
        observation_bright_limit_low = None
        observation_bright_limit_high = None
        
        sources_insert_list = ["INSERT INTO observations (source_id, instrument_id , filter_id , user_id , observation_ucd , observation_units , observation_time_format , observation_time_scale , observation_description , observation_bright_limit_low , observation_bright_limit_high , observation_start , observation_end) VALUES "]
        for hip_id, hip_dict in debos_subset.iteritems():
            source_id = hip_dict['new_srcid']
            observation_start = min(hip_dict['t'])
            observation_end = max(hip_dict['t'])
            if observation_start > 2000000:
                observation_time_format = 'jd'
            else:
                observation_time_format = 'tjd' # This is used by project_id=122 (tjd)
                
            insert_tup = (source_id, instrument_id , filter_id , user_id , observation_ucd , observation_units , observation_time_format , observation_time_scale , observation_description , observation_bright_limit_low , observation_bright_limit_high , observation_start , observation_end)

            sources_insert_list.append("""(%d, %d, %d, %d, '%s', '%s', '%s', %d, '%s', '%s', '%s', %lf, %lf), """ %  insert_tup)
        sources_insert_str = ''.join(sources_insert_list)[:-2]
        
        if debug:
            #print sources_insert_str
            for elem in sources_insert_list:
                print(elem)
            #print sources_insert_list[0]
            #print sources_insert_list[1]
            #print sources_insert_list[2]
            #print sources_insert_list[3]
        else:
            print(sources_insert_list[0])
            print(sources_insert_list[1])
            print(sources_insert_list[2])
            print(sources_insert_list[3])
            print('INSERTing: ...')
            self.cursor.execute(sources_insert_str)



    def insert_into_obsdata_table__deboss(self, debug=True, debos_subset={}):
        """  Using observation_id, insert m,t,merr info into table.
        """
        import pdb; pdb.set_trace()
        obsdata_limit = False
        obsdata_limit_sigma = 0
        for hip_id, hip_dict in debos_subset.iteritems():
            observation_id = hip_dict['new_observationid']

            sources_insert_list = ["INSERT INTO obs_data (observation_id, obsdata_time, obsdata_val, obsdata_err, obsdata_limit, obsdata_limit_sigma) VALUES "]

            for i in xrange(len(hip_dict['t'])):
                obsdata_time = hip_dict['t'][i]
                obsdata_val = hip_dict['m'][i]
                obsdata_err = hip_dict['merr'][i]
                insert_tup = (observation_id, obsdata_time, obsdata_val, obsdata_err, obsdata_limit, obsdata_limit_sigma)
                sources_insert_list.append("""(%d, %lf, %lf, %lf, '%s', %d), """ %  insert_tup)
            sources_insert_str = ''.join(sources_insert_list)[:-2]
        
            if debug:
                #print sources_insert_str
                print(sources_insert_list[0])
                print(sources_insert_list[1])
                print(sources_insert_list[2])
                print(sources_insert_list[3])
                import pdb; pdb.set_trace()
            else:
                print(sources_insert_list[0])
                print(sources_insert_list[1])
                print(sources_insert_list[2])
                print(sources_insert_list[3])
                print('INSERTing: ...')
                self.cursor.execute(sources_insert_str)


    def select_observation_ids__deboss(self, debos_subset={}):
        """
        select observation_id from observations table
        """
        for hip_id, hip_dict in debos_subset.iteritems():
            
            select_str = "SELECT observation_id FROM observations WHERE source_id=%d" % \
                             (hip_dict['new_srcid'])
            self.cursor.execute(select_str)
            results = self.cursor.fetchall()
            assert(len(results) == 1)
            hip_dict['new_observationid'] = results[0][0]



    def insert_HIP_objects_into_tables(self, debug=True, debos_subset={}, class_name_id_dict={}):
        """ Insert object, epoch data from older project entries into new table

        NOTE: This or a previous function will retrieve the old_project objects, epochs from RDB

        NOTE: There will be ~200 new objects that will need to be INSERTED into the RDB.

        Insert into:
           sources       # AUTO source_id, project_id, class_id, pclass_id
           observations  # AUTO observation_id, source_id, instrument_id, filter_id
           obs_data      # observation_id, obsdata_time
           
        """
        data_with_tutorids = {}
        data_without_tutorids = {}
        for hip_id, hip_dict in debos_subset.iteritems():
            if 'tutorid' in hip_dict:
                data_with_tutorids[hip_id] = hip_dict
            else:
                data_without_tutorids[hip_id] = hip_dict

        if 0:
            # Do once only:
            self.insert_known_sources_into_tables(debug=True, data_with_tutorids=data_with_tutorids,
                                              class_name_id_dict=class_name_id_dict)
            self.insert_new_sources_into_tables(debug=True, data_without_tutorids=data_without_tutorids,
                                              class_name_id_dict=class_name_id_dict)
        self.select_sourceids__deboss(debos_subset=debos_subset)
        if 0:
            # Do once only:
            self.insert_into_observations_table__deboss(debug=True, debos_subset=debos_subset)
        self.select_observation_ids__deboss(debos_subset=debos_subset)
        if 0:
            # Do once only:
            self.insert_into_obsdata_table__deboss(debug=True, debos_subset=debos_subset)


    def get_ogle_src_info_from_oldproj_table(self, debos_subset={}):
        """
        # TODO get a list of all get(['tutorid'],'') != '' # which are proj 122 HIP
        # TODO query proj 122 sources table for all unmatched sources
        # print / ensure that these unmatched sources are all OGLE (and there are no HD / HIP)
        """
        old_hip_srcids = []
        for hip_id, hip_dict in debos_subset.iteritems():
            if 'tutorid' in hip_dict:
                old_hip_srcids.append(hip_dict['tutorid'])
                #print hip_dict['tutorid'], hip_dict['tutor_name'], hip_dict['xml']

        # the following tcp_srcids are in proj=122, are HIPPARCOS but were determined to be either:
        #   - skippable by Josh's determination that the science class is not discernable
        #        -> 148163, 148210, 148229, 148253, 148395, 148402, 148741
        #   - or are PVSG without ra,dec in arien's hip_head_new.txt file
        #        -> 148842, 148843, 148844, 148845, 148846, 148847, 148848, 148849, 148850, 148851, 148852, 148853, 148854, 148855, 148856, 148857, 148858, 148859, 148860, 148861, 148862, 148863, 148864, 148865
        #   - or are duplicates of HIP sources already in proj=122
        #        -> 161326, 161327, 161328, 161329, 161330, 161331, 161332, 161333, 161334, 161335, 161336, 161337, 161338,     148841
        skip_srcids = [148163, 148210, 148229, 148253, 148395, 148402, 148741, 148842, 148843, 148844, 148845, 148846, 148847, 148848, 148849, 148850, 148851, 148852, 148853, 148854, 148855, 148856, 148857, 148858, 148859, 148860, 148861, 148862, 148863, 148864, 148865, 161326, 161327, 161328, 161329, 161330, 161331, 161332, 161333, 161334, 161335, 161336, 161337, 161338, 148841]

        ogle_oldsrcid_srcname_dict = {}

        select_str = "SELECT source_id, source_name, class_id, pclass_id FROM sources WHERE project_id=%d" % (\
                              self.pars['old_proj_id'])
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        for (source_id, source_name, class_id, pclass_id) in results:
            if ((not source_id in old_hip_srcids) and
                (not source_id in skip_srcids)):
                #print source_id, source_name
                ogle_oldsrcid_srcname_dict[source_id] = {'tutorid':source_id,
                                                         'tutor_name':source_name,
                                                         'pclass_id':pclass_id,
                                                         'class_id':class_id}
        return ogle_oldsrcid_srcname_dict



    def parse_tme_dat(self, dat_fpath):
        """  Parse the debisscher OGLE dat files.
        """
        lines = open(dat_fpath).readlines()
        out = {'t':[], 'm':[], 'merr':[]}

        for line in lines:
            tups = line.split()
            out['t'].append(float(tups[0]))
            out['m'].append(float(tups[1]))
            out['merr'].append(float(tups[2]))

        return out


    def parse_dat_ts_for_ogle_sources(self, data_dict={}):
        """
        """
        #dat_fpaths = glob.glob("%s/OGLE*" % (self.pars['old_proj122_ogle_dat_dirpath']))
        dat_fpaths = glob.glob("%s/*dat" % (self.pars['old_proj122_ogle_dat_dirpath']))
        for dat_fpath in dat_fpaths:
            fname = dat_fpath[dat_fpath.rfind('/')+1:dat_fpath.rfind('.dat')]
            match_found = False
            for k,v in data_dict.iteritems():
                if (('OGLE' in fname) and
                    (v['tutor_name'] == fname)):
                    #print fname, k, v
                    # TODO: here we need to parse the t,m,merr and place in dictionary
                    tme_dict = self.parse_tme_dat(dat_fpath)
                    v.update(tme_dict)
                    match_found = True
                    break
                elif v['tutor_name'][-len(fname):] == fname:
                    #print '!!!', fname, k, v
                    tme_dict = self.parse_tme_dat(dat_fpath)
                    v.update(tme_dict)
                    match_found = True
                    break
            if fname == '13365':
                print('yo', fname, k, v)
                #import pdb; pdb.set_trace()
            if match_found == False:
                print('NO MATCH:', fname)
                raise



    def insert_nonHIP_objects_into_tables(self, debug=True, debos_subset={}, class_name_id_dict={}):
        """  Insert OGLE sources into new project 123 tables.
        
        For now we assume that all OGLE sources should be imported, and use the original classifications.
        """
        ogle_data_dict = self.get_ogle_src_info_from_oldproj_table(debos_subset=debos_subset)

        # # # # # TODO:
        # TODO: first insert 'xml' into dicts
        self.parse_dat_ts_for_ogle_sources(data_dict=ogle_data_dict)
        #self.parse_add_timeseries_data_from_files(debos_subset=debos_subset)
        # #  # #

        if 0:
            # Do once only:
            self.insert_known_sources_into_tables(debug=True, data_with_tutorids=ogle_data_dict,
                                                  class_name_id_dict=class_name_id_dict)

        
        # TODO proceed to retrieve all info and insert these sources into 123

        self.select_sourceids_ogle(debos_subset=ogle_data_dict)
        if 0:
            # Do once only:
            self.insert_into_observations_table__deboss(debug=True, debos_subset=ogle_data_dict)
        self.select_observation_ids(debos_subset=ogle_data_dict)
        if 0:
            # Do once only:
            self.insert_into_obsdata_table__deboss(debug=True, debos_subset=ogle_data_dict)

        import pdb; pdb.set_trace()



    def data_sanity_checks(self):
        """
        # TODO: check that RDB source data for some sources is identical to proj=122
        # TODO: check that RDB the expected number of sources exist in proj=123
        # TODO: check that RDB the expected classes are contained in RDB
        # TODO: check that the resulting xmls from populate_feat_db_using_TUTOR.py match existing xmls, feats

        """
        pass



    def query_build_class_name_id_dict(self, project_id=122):
        """
        # Get the class lookup from strings to class_id, pclass_id
        #  - I suppose I can narrow these classes to only ones that project=122 used
        """

        ### This gets only classes for a project_id which there are sources for:
        ___select_str = """
SELECT DISTINCT sources.pclass_id, pclass_short_name FROM sources
JOIN project_classes USING (pclass_id, project_id)
WHERE sources.project_id=%d
ORDER BY sources.pclass_id;
        """ % (project_id)
        ###This gets all classes for a project_id:
        select_str = "SELECT pclass_short_name, pclass_id, class_id FROM project_classes WHERE project_id=%d" % (project_id)

        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        class_name_id_dict = {}
        for row in results:
            class_name_id_dict[row[0]] = {'pclass_id':row[1], 'class_id':row[2]}
        return class_name_id_dict
    

    def debosscher_main(self, debug=True):
        """
        # This was used in ~2010-12-20

        Flag:
              debug=True  # Create TEMPORARY TABLE
        """
        
        if 0:
            # Do this only once (DONE):
            proj_tables = self.get_existing_project_table_info()
            self.insert_into_project_tables(debug=True,  ###NOTE: we've already done this once
                                        proj_tables=proj_tables)  #NOTE: disabling this should be fine if done once already
        class_name_id_dict = self.query_build_class_name_id_dict( \
                               project_id=self.pars['new_proj_id'])
        
        ####### TODO: need to get upt to this point (insert into project tables)
        # ... then disable those functions?
        
        if not os.path.exists(self.pars['hipdict_with_ts_pklgz_fpath']):
            debos_subset = self.get_josh_deboss_data_subset()
            self.parse_add_timeseries_data_from_files(debos_subset=debos_subset)

            fp = gzip.open(self.pars['hipdict_with_ts_pklgz_fpath'],'wb')
            cPickle.dump(debos_subset,fp,1) # ,1) means a binary pkl is used.
            fp.close()
            
        else:
            fp=gzip.open(self.pars['hipdict_with_ts_pklgz_fpath'],'rb')
            debos_subset=cPickle.load(fp)
            fp.close()
            
        #BROKE# self.insert_HIP_objects_into_tables(debug=True, debos_subset=debos_subset, class_name_id_dict=class_name_id_dict)
        self.insert_nonHIP_objects_into_tables(debug=True, debos_subset=debos_subset, class_name_id_dict=class_name_id_dict)
        self.data_sanity_checks()


class TimeseriesInsert(TutorDb):
    """ Assuming the sources for a project have already been added to TUTOR
    (say using the TUTOR web GUI)
     - This class has code which imports the timeseries data.
    """

    def parse_source_data(self, fpath='', delimiter='', dtype={}):
        """
        """
        from numpy import loadtxt
        
        if len(delimiter) == 0:
            delimiter = self.pars['delimiter']
        if len(dtype) == 0:
            dtype = self.pars['dtype']
        
        d = loadtxt(fpath, delimiter=delimiter,
                    dtype=dtype)

        return d


    def parse_124_ts_data(self, fpath):
        """ Custom parser of project_id=124 TS data files
         - first 2 lines are header
         - each empty line denotes new filter
         - filters of this ordering:
             V
             U-B
             B-V
             V-R
        
        """
        filters = {0:'V',
                   1:'U-B',
                   2:'B-V',
                   3:'V-R'}


        ts_lists = {'V':{'t':[], 'm':[]},
                   'U-B':{'t':[], 'm':[]},
                   'B-V':{'t':[], 'm':[]},
                   'V-R':{'t':[], 'm':[]}}

        ts_dicts = {'V':{},
                   'U-B':{},
                   'B-V':{},
                   'V-R':{}}

        lines = open(fpath).readlines()

        i_filt = 0
        for raw_line in lines[2:]:
            line = raw_line.strip()
            if len(line) == 0:
                i_filt += 1
                continue
            (t, m) = line.split()
            ts_lists[filters[i_filt]]['t'].append(t)
            ts_lists[filters[i_filt]]['m'].append(m)
            
            ts_dicts[filters[i_filt]][t] = m  # these are strings

        assert(len(ts_lists['V']['t']) > 0)


        out_dict = {}
        out_dict['V'] = {'m':[],
                         't':[]}
        for t in ts_lists['V']['t']:
            out_dict['V']['m'].append(float(ts_dicts['V'][t]))
            out_dict['V']['t'].append(float(t))


        if len(ts_lists['V-R']['m']) > 0:
            out_dict['R'] = {'m':[],
                             't':[]}
            for t in ts_lists['V-R']['t']:
                out_dict['R']['m'].append(float(ts_dicts['V'][t]) - float(ts_dicts['V-R'][t]))
                out_dict['R']['t'].append(float(t))


        if len(ts_lists['B-V']['m']) > 0:
            out_dict['B'] = {'m':[],
                             't':[]}
            for t in ts_lists['B-V']['t']:
                out_dict['B']['m'].append(float(ts_dicts['B-V'][t]) + float(ts_dicts['V'][t]))
                out_dict['B']['t'].append(float(t))


        if len(ts_lists['U-B']['m']) > 0:
            assert(len(ts_lists['B-V']['m']) > 0)
            
            out_dict['U'] = {'m':[],
                             't':[]}
            for t in ts_lists['U-B']['t']:
                try:
                    out_dict['U']['m'].append(float(ts_dicts['U-B'][t]) + float(ts_dicts['B-V'][t]) + float(ts_dicts['V'][t]))
                    out_dict['U']['t'].append(float(t))
                except:
                    print(" !!! MISSING B-V (%s): t=%s V=%s U-B=%s" % (fpath[fpath.rfind('/')+1:],
                                                                  t,
                                                                  ts_dicts['V'][t],
                                                                  ts_dicts['U-B'][t]))


        return out_dict
    


    def parse_128_ts_data(self, fpath):
        """ Custom parser of project_id=128 (Sasir stripe82 SDSS RRLyrae) TS data files

        OUTPUT:
        out_dict[<filter>]{'m':[],
                           't':[],
        
        """
        delimiter = ' '
        dtype = {'names':('ra', 'dec', 't_u', 'm_u', 'merr_u', 't_g', 'm_g', 'merr_g', 't_r', 'm_r', 'merr_r', 't_i', 'm_i', 'merr_i', 't_z', 'm_z', 'merr_z'),
               'formats':('f8', 'f8',  'f8',  'f8',  'f8',     'f8',  'f8',  'f8',     'f8',  'f8',  'f8',     'f8',  'f8',  'f8',     'f8',  'f8',  'f8')}

        data = self.parse_source_data(fpath=fpath, delimiter=delimiter, dtype=dtype)

        out_dict = {}

        #for filt_name in ['u', 'g', 'r', 'i', 'z']:
        for filt_name in ['U', 'G', 'R', 'I', 'z']:
            if filt_name not in out_dict:
                out_dict[filt_name] = {'t':[],
                                       'm':[],
                                       'merr':[]}

        for i in range(len(data['ra'])):
            for filt_name in ['U', 'G', 'R', 'I', 'z']:
                filt_lowercase = filt_name.lower()
                out_dict[filt_name]['t'].append(data["t_%s" % (filt_lowercase)][i])
                out_dict[filt_name]['m'].append(data["m_%s" % (filt_lowercase)][i])
                out_dict[filt_name]['merr'].append(data["merr_%s" % (filt_lowercase)][i])

        return out_dict


    def parse_ts_files(self, source_ndarray):
        """ using the given source-info ndarray data, find timeseries data and parse into dict.
        """
        source_data = {}

        # DEBUG for i, raw_fname in enumerate(source_ndarray[self.pars['ts_filename_colname']][:2]):
        for i, raw_fname in enumerate(source_ndarray[self.pars['ts_filename_colname']]):
            fname = str(raw_fname).strip()
            fpath = "%s/%s%s" % (self.pars['ts_data_dirpath'], fname, self.pars['ts_filename_suffix'])

            if self.pars['project_id'] == 124:
                ts_data = self.parse_124_ts_data(fpath)
            elif self.pars['project_id'] == 128:
                ts_data = self.parse_128_ts_data(fpath)
            
            source_name = str(source_ndarray[self.pars['ts_source_colname']][i]).strip()

            source_data[source_name] = {'fname':fname,
                                        'ts_data':ts_data,
                                        'source_name':source_name}
        return source_data


    def insert_sources(self, source_data={}, project_id=None):
        """ Insert the sources into TUTOR source table.

        NOTE: need to have the project added to TUTOR database via tutor-website
        """
        select_str = "SELECT max(source_id) from sources"
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        srcid_max = results[0][0]
        
        srcname_srcid_dict = {}
        insert_list = ["INSERT INTO sources (source_id, source_oid, project_id, source_name, source_ra, source_dec, source_ra_err, source_dec_err, source_epoch, class_id, pclass_id) VALUES "]
        import pdb; pdb.set_trace()
        print()
        cur_srcid = srcid_max + 1
        for src_name, src_dict in source_data.iteritems():
            insert_list.append('(%d, "%s", %d, "%s", %lf, %lf, 0.0, 0.0, "J2000.0", 0, 0), ' % ( \
                cur_srcid,
                src_name,
                project_id,
                src_name,
                src_dict['ts_data']['V']['ra'],
                src_dict['ts_data']['V']['dec']))

            srcname_srcid_dict[src_name] = int(cur_srcid)
            cur_srcid += 1
            if len(insert_list) > 10000:
                insert_str = ''.join(insert_list)[:-2]# + " ON DUPLICATE KEY UPDATE retrieved=VALUES(retrieved)"
                #import pdb; pdb.set_trace()
                #print 
                self.cursor.execute(insert_str)
                insert_list = ["INSERT INTO sources (source_id, source_oid, project_id, source_name, source_ra, source_dec, source_ra_err, source_dec_err, source_epoch, class_id, pclass_id) VALUES "]

        if len(insert_list) > 1:
            insert_str = ''.join(insert_list)[:-2]# + " ON DUPLICATE KEY UPDATE retrieved=VALUES(retrieved)"
            #import pdb; pdb.set_trace()
            #print 
            self.cursor.execute(insert_str)
        return srcname_srcid_dict


    # OBSOLETE:  note that the following was used to insert proj=126 ASAS into lyra:tutor database, but that the oid used was just an incremented integer, which is wrong since cur_src_oid is varchar() and the SELECT MAX(source_oid) returns buggy answers.  In a new implementation of this function we just use the src_name for the cur_src_oid.
    def insert_sources__pre20120103(self, source_data={}, project_id=None):
        """ Insert the sources into TUTOR source table.

        NOTE: need to have the project added to TUTOR database via tutor-website
        """
        select_str = "SELECT max(source_id) from sources"
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        srcid_max = results[0][0]
        
        select_str = "SELECT max(source_oid) from sources where project_id=%d" % (self.pars['project_id'])
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        src_oid_max = results[0][0]
        if src_oid_max is None:
            cur_src_oid = 0
        else:
            cur_src_oid = int(src_oid_max) + 1

        srcname_srcid_dict = {}
        insert_list = ["INSERT INTO sources (source_id, source_oid, project_id, source_name, source_ra, source_dec, source_ra_err, source_dec_err, source_epoch, class_id, pclass_id) VALUES "]
        cur_srcid = srcid_max + 1
        for src_name, src_dict in source_data.iteritems():
            insert_list.append('(%d, %d, %d, "%s", %lf, %lf, 0.0, 0.0, "J2000.0", 0, 0), ' % ( \
                cur_srcid,
                cur_src_oid,
                project_id,
                src_name,
                src_dict['ts_data']['V']['ra'],
                src_dict['ts_data']['V']['dec']))

            srcname_srcid_dict[src_name] = int(cur_srcid)
            cur_srcid += 1
            cur_src_oid += 1
            if len(insert_list) > 10000:
                insert_str = ''.join(insert_list)[:-2]# + " ON DUPLICATE KEY UPDATE retrieved=VALUES(retrieved)"
                #import pdb; pdb.set_trace()
                #print 
                self.cursor.execute(insert_str)
                insert_list = ["INSERT INTO sources (source_id, source_oid, project_id, source_name, source_ra, source_dec, source_ra_err, source_dec_err, source_epoch, class_id, pclass_id) VALUES "]

        if len(insert_list) > 1:
            insert_str = ''.join(insert_list)[:-2]# + " ON DUPLICATE KEY UPDATE retrieved=VALUES(retrieved)"
            #import pdb; pdb.set_trace()
            #print 
            self.cursor.execute(insert_str)
        return srcname_srcid_dict


    def main(self, source_data={}):
        """ Main for TimeseriesInsert(TutorDb) class
        """
        if len(source_data) == 0:
            source_ndarray = self.parse_source_data(fpath=self.pars['source_data_fpath'])
            source_data = self.parse_ts_files(source_ndarray)

        if 0:
            ### the sources dont exist in tutor source table, so we insert:
            sourceid_lookup = self.insert_sources(source_data=source_data,
                                                  project_id=self.pars['project_id'])
        else:
            ### The sources do exist in the tutor source table
            sourceid_lookup = self.query_sourcename_sourceid_lookup(project_id=self.pars['project_id'])

        self.update_with_sourceids(sourceid_lookup=sourceid_lookup, source_data=source_data)

        if 1:
            # Do once only:
            self.insert_into_observations_table(debug=False, source_data=source_data,
                                                instrument_id = 0,
                                                user_id = self.pars['user_id'],
                                                observation_ucd = 'phot.mag',
                                                observation_units = 'mag',
                                                observation_time_scale = 1,
                                                observation_description = 'c',
                                                observation_bright_limit_low = None,
                                                observation_bright_limit_high = None)
        self.select_observation_ids(source_data=source_data)
        if 0:
            # if the sources exist in observations table already, here we just update the observation_start, observation_end info.
            self.update_observations_table(debug=False, source_data=source_data,
                                                instrument_id = 0,
                                                user_id = self.pars['user_id'],
                                                observation_ucd = 'phot.mag',
                                                observation_units = 'mag',
                                                observation_time_scale = 1,
                                                observation_description = 'c',
                                                observation_bright_limit_low = None,
                                                observation_bright_limit_high = None)
        if 0:
            # Do once only:
            #import pdb; pdb.set_trace()
            #print
            self.insert_into_obsdata_table(debug=False, source_data=source_data,
                                           delete_entries_first=True, # Do this only if we are updating timeseries values for existing sources
                                           insert_limits=False)  # False: do not insert upper_limits into obs_data

class ASAS_Data_Tools:
    """ Tools needed for retrieving ASAS data.

    """
    def __init__(self, pars={}):
        self.pars = pars


    def initialize_frame_mag_tally_dict(self):
        """ This will get large: 350k dict entries
        and is updated using update_frame_mag_tally()
        """
        n_fields = 350000 # The limit is 334991
        self.frame_mag_tally = {'frame':numpy.arange(n_fields, dtype=numpy.int32),
                                'n':numpy.zeros((n_fields), dtype=numpy.int32), #2**15 -1 = 32767 max
                                'n_c_lim':numpy.zeros((n_fields), dtype=numpy.int32),
                                'n_c_nolim':numpy.zeros((n_fields), dtype=numpy.int32),
                                'n_d':numpy.zeros((n_fields), dtype=numpy.int32),
                                'm_avg':numpy.zeros((n_fields), dtype=numpy.float32), #12.123456
                                'm_var':numpy.zeros((n_fields), dtype=numpy.float32), #12.123456
                                'm0':numpy.zeros((n_fields), dtype=numpy.float32), #12.123456
                                'm1':numpy.zeros((n_fields), dtype=numpy.float32), #12.123456
                                'm2':numpy.zeros((n_fields), dtype=numpy.float32), #12.123456
                                'm3':numpy.zeros((n_fields), dtype=numpy.float32), #12.123456
                                'm4':numpy.zeros((n_fields), dtype=numpy.float32), #12.123456
                                }


    def update_frame_mag_tally_table(self):
        """ Insert/update the frame_mag_tally information int tranx mysql table.

        CREATE TABLE asas_fullcat_frame_limits
        (frame MEDIUMINT,
         n MEDIUMINT UNSIGNED,
         n_c_lim MEDIUMINT UNSIGNED,
         n_c_nolim MEDIUMINT UNSIGNED,
         n_d MEDIUMINT UNSIGNED,
         m_avg FLOAT,
         m_var FLOAT,
         m0 FLOAT,
         m1 FLOAT,
         m2 FLOAT,
         m3 FLOAT,
         m4 FLOAT,
         m_p98 FLOAT, 
         m_p95 FLOAT, 
         m_p93 FLOAT, 
         m_p90 FLOAT, 
         m_p80 FLOAT, 
         m_p70 FLOAT, 
         m_p60 FLOAT, 
         m_p50 FLOAT, 
         m_p40 FLOAT, 
         m_p30 FLOAT, 
         m_p20 FLOAT, 
         m_p10 FLOAT,
         PRIMARY KEY (frame));
        
        """
        self.tcp_db = MySQLdb.connect(host=self.pars['tcp_hostname'], \
                                  user=self.pars['tcp_username'], \
                                  db=self.pars['tcp_database'],\
                                  port=self.pars['tcp_port'])
        self.tcp_cursor = self.tcp_db.cursor()

        
        insert_list = ["INSERT INTO asas_fullcat_frame_limits (frame, n, n_c_lim, n_c_nolim, n_d, m_avg, m_var, m0, m1, m2, m3, m4) VALUES "]

        for frame_id in self.frame_mag_tally['frame']:
            if (int(self.frame_mag_tally['n'][frame_id]) < 1) and (float(self.frame_mag_tally['m0'][frame_id]) > 0.1):
                ### debug
                import pdb; pdb.set_trace()
                print()
            insert_list.append('(%d, %d, %d, %d, %d, %lf, %lf, %lf, %lf, %lf, %lf, %lf), ' % (frame_id,
                                                                                  self.frame_mag_tally['n'][frame_id],
                                                                                  self.frame_mag_tally['n_c_lim'][frame_id],
                                                                                  self.frame_mag_tally['n_c_nolim'][frame_id],
                                                                                  self.frame_mag_tally['n_d'][frame_id],
                                                                                  self.frame_mag_tally['m_avg'][frame_id],
                                                                                  self.frame_mag_tally['m_var'][frame_id],
                                                                                  self.frame_mag_tally['m0'][frame_id],
                                                                                  self.frame_mag_tally['m1'][frame_id],
                                                                                  self.frame_mag_tally['m2'][frame_id],
                                                                                  self.frame_mag_tally['m3'][frame_id],
                                                                                  self.frame_mag_tally['m4'][frame_id]))

            if len(insert_list) > 10000:
                print('insert > 100000', frame_id)
                insert_str = ''.join(insert_list)[:-2] + " ON DUPLICATE KEY UPDATE n=VALUES(n), n_c_lim=VALUES(n_c_lim), n_c_nolim=VALUES(n_c_nolim), n_d=VALUES(n_d), m_avg=VALUES(m_avg), m_var=VALUES(m_var), m0=VALUES(m0), m1=VALUES(m1), m2=VALUES(m2), m3=VALUES(m3), m4=VALUES(m4)"
                #import pdb; pdb.set_trace()
                #print
                self.tcp_cursor.execute(insert_str)
                insert_list = ["INSERT INTO asas_fullcat_frame_limits (frame, n,  n_c_lim, n_c_nolim, n_d, m_avg, m_var, m0, m1, m2, m3, m4) VALUES "]

        if len(insert_list) > 1:
            insert_str = ''.join(insert_list)[:-2] + " ON DUPLICATE KEY UPDATE n=VALUES(n), n_c_lim=VALUES(n_c_lim), n_c_nolim=VALUES(n_c_nolim), n_d=VALUES(n_d), m_avg=VALUES(m_avg), m_var=VALUES(m_var), m0=VALUES(m0), m1=VALUES(m1), m2=VALUES(m2), m3=VALUES(m3), m4=VALUES(m4)"
            #import pdb; pdb.set_trace()
            #print
            self.tcp_cursor.execute(insert_str)

        #import pdb; pdb.set_trace()
        #print 
        self.tcp_cursor.close()
        

    def retrieve_fullcat_frame_limitmags(self):
        """ Retrieve a mag_limt(frame_id) dictionary from the tranx RDB table:
        asas_fullcat_frame_limits

        NOTE: This and update_frame_mag_tally_table() could probably be in their own class
            - since they perform actions related to limiting-mags
            - and since they are the only functions using tranx-RDB

       TODO: eventually this will use the m0,m1,m2... information in a consistant way
             in order to estimate the limiting mag, independent of n, m_var.

        """
        self.tcp_db = MySQLdb.connect(host=self.pars['tcp_hostname'], \
                                  user=self.pars['tcp_username'], \
                                  db=self.pars['tcp_database'],\
                                  port=self.pars['tcp_port'])
        self.tcp_cursor = self.tcp_db.cursor()

        self.frame_limitmags = {}

        ### KLUDGE: for now we just use the 2nd to last, deepest mag:
        #pre20111221#select_str = "SELECT frame, m1 FROM asas_fullcat_frame_limits WHERE n >= 20"# % ()
        #pre20120220#select_str = "SELECT frame, m_p95 FROM asas_fullcat_frame_limits WHERE n >= 20"# % ()
        select_str = "SELECT frame, m0 FROM asas_fullcat_frame_limits WHERE n >= 20"# % ()

        self.tcp_cursor.execute(select_str)

        results = self.tcp_cursor.fetchall()
        for row in results:
            (frame, limit_mag) = row
            self.frame_limitmags[frame] = limit_mag
        self.tcp_cursor.close()


    def update_asas_source_ra_dec(self):
        """ update the ra, dec for asas sources
        """
        from numpy import loadtxt, sqrt, cos, pi
        self.tutor_db = MySQLdb.connect(host=self.pars['tcptutor_hostname'],
                                        user=self.pars['tcptutor_username'], 
                                        db=self.pars['tcptutor_database'],
                                        port=self.pars['tcptutor_port'],
                                        passwd=self.pars['tcptutor_password'])
        self.tutor_cursor = self.tutor_db.cursor()

        d = loadtxt(self.pars['new_source_tutoringest_fpath'],
                    delimiter='\t',
                    dtype={'names':('oid','name','class','ra','dec'), \
                           'formats':('i8', 'S13','S5','f8','f8')})

        insert_list = ["INSERT INTO sources (source_id, source_ra, source_dec) VALUES "]

        #fp_radec = open('/home/dstarr/scratch/asas_acvs_radec_diff', 'w')
        select_str = "select source_id, source_oid, source_name, source_ra, source_dec from sources where project_id=126 order by source_id"
        self.tutor_cursor.execute(select_str)
        results = self.tutor_cursor.fetchall()
        for row in results:
            (tutor_id, tutor_oid, tutor_name, old_ra, old_dec) = row
            old_ra = float(old_ra)
            old_dec = float(old_dec)
            
            i = numpy.where(d['name'] == tutor_name)
            assert(int(tutor_oid) == d['oid'][i])
            ra = d['ra'][i][0]
            dec = d['dec'][i][0]

            #fp_radec.write("%d %lf %lf %lf %lf %lf\n" % (tutor_id,
            #                                             ra,
            #                                             dec,
            #                                             sqrt(((ra - old_ra)**2)*(cos(dec*pi/180.)**2) + (dec - old_dec)**2),
            #                                             ra - old_ra,
            #                                             dec - old_dec))

            insert_list.append('(%d, %lf, %lf), ' % (tutor_id, ra, dec))
            if len(insert_list) > 10000:
                insert_str = ''.join(insert_list)[:-2] + " ON DUPLICATE KEY UPDATE source_ra=VALUES(source_ra), source_dec=VALUES(source_dec)"
                #import pdb; pdb.set_trace()
                #print
                self.tutor_cursor.execute(insert_str)
                insert_list = ["INSERT INTO sources (source_id, source_ra, source_dec) VALUES "]
        if len(insert_list) > 1:
            insert_str = ''.join(insert_list)[:-2] + " ON DUPLICATE KEY UPDATE source_ra=VALUES(source_ra), source_dec=VALUES(source_dec)"
            #import pdb; pdb.set_trace()
            #print 
            self.tutor_cursor.execute(insert_str)

        #fp_radec.close()
        import pdb; pdb.set_trace()
        print() 


    def convert_ra_hrs_to_deg(self):
        """ ASAS RA in database is in decimal hours rather than decimal degress.
        This code queries the database and updates this RA value.

        NOTE: I just ran this command by hand so this function is incomplete.
        """

        update_str = "UPDATE sources SET source_ra=source_ra*15.0 WHERE project_id=126" % ()

        self.cursor.execute(select_str)
        results = self.cursor.fetchall()



    def get_asas_timeseries_for_url(self, url=""):
        """ derived from download_timeseries_datasets_from_web()
        """

        import urllib
        import matplotlib.pyplot as pyplot

        f_url = urllib.urlopen(url)
        ts_str = f_url.read()
        f_url.close()
        #f_disk = open(ts_fpath, 'w')
        #f_disk.write(ts_str)
        #f_disk.close()
        source_intermed_dict = self.parse_asas_ts_data_str(ts_str)
        v_mag = self.filter_best_ts_aperture(source_intermed_dict)
        import pdb; pdb.set_trace()
        print() 
        


    def retrieve_parse_asas_acvs_source_data(self):
        """ Parse source (not timeseries) data from file.

        NOTE: I had to change the comment lines to '###' since some of the
              source identifiers use '#'

        """
        from numpy import loadtxt
        source_ndarray = loadtxt(self.pars['source_data_fpath'], comments='###',
                    dtype={'names':('ID','PER','HJD0','VMAX','VAMP','TYPE','GCVS_ID','GCVS_TYPE',
                                    'IR12','IR25','IR60','IR100','J','H','K',
                                    'V_IR12','V_J','V_H','V_K','J_H','H_K'), \
                         'formats':('S13','f8','f8','f8','f8','S20','S20','S20',
                                    'f8','f8','f8','f8','f8','f8','f8',
                                    'f8','f8','f8','f8','f8','f8')})
        return source_ndarray


    def retrieve_fullcatalog_source_dict(self):
        """ General non-variable fullcatalog ASAS sources case.
        - essentially just get source_name from filename
        """
        import glob
        source_dict = {'ID':[],
                       'TYPE':[],
                       }

        db = MySQLdb.connect(host=self.pars['tcptutor_hostname'],
                                  user=self.pars['tcptutor_username'],
                                  db=self.pars['tcptutor_database'],
                                  port=self.pars['tcptutor_port'],
                                  passwd=self.pars['tcptutor_password'])
        cursor = db.cursor()

        select_str = "SELECT source_name FROM sources WHERE project_id=%d" % (self.pars['project_id'])
        cursor.execute(select_str)
        existing_sources = []
        results = cursor.fetchall()
        for row in results:
            existing_sources.append(row[0])

        ### list of files not sorted by mod-time:
        #glob_str = "%s/*.dat" % (self.pars['asas_timeseries_dirpath'])
        #fpaths = glob.glob(glob_str)

        ### list of files sorted by mod-time:
        def sorted_ls(path):
            mtime = lambda f: os.stat(f).st_mtime
            fullpaths = map(lambda fname: os.path.join(path, fname), os.listdir(path))
            return list(sorted(fullpaths, key=mtime))
        fpaths = sorted_ls(self.pars['asas_timeseries_dirpath'])        

        for fpath in fpaths:
            #proj131: source_name = fpath[fpath.rfind('/') + 1:fpath.rfind('.')]
            source_name = fpath[fpath.rfind('/') + 1:] # proj 126 # asas 50k
            if source_name in existing_sources:
                print("ALREADY in TUTOR.sources!", source_name)
                #import pdb; pdb.set_trace()
                #print 
                continue
            source_dict['ID'].append(source_name)
            source_dict['TYPE'].append('')

        # # # TODO: want to exclude project=131 sources
        #  - assuming no project_126 since these sources were not retrieved from the web
        #  - TODO retrieve all src_names for proj-131 and assert that non of hte added sourced_dict['ID'] are these
        #  - then there will be no chance of inserting source_names which already exist in TUTOR sources table.
        cursor.close()
        return source_dict



    def get_sub_ts_ndarray(self, ts_sublist, ts_col_names=[]):
        """
        """
        from numpy import loadtxt
        from io import StringIO
        dtype_lookup = { \
            'HJD'  :'f8',  
            'MAG_3':'f8',
            'MAG_0':'f8',
            'MAG_1':'f8',
            'MAG_2':'f8',
            'MAG_4':'f8',
            'MER_3':'f8',
            'MER_0':'f8',
            'MER_1':'f8',
            'MER_2':'f8',
            'MER_4':'f8',
            'GRADE':'S1',
            'FRAME':'i8',
            'FLAG' :'i8'}

        ts_substr = '\n'.join(ts_sublist)
        fp_strio = StringIO(ts_substr)
        ts_dtypes = map(lambda x: str(dtype_lookup[x]), ts_col_names)
            
        ts_ndarray = loadtxt(fp_strio, comments='#',
                     dtype={'names':ts_col_names,
                            'formats': ts_dtypes})
        fp_strio.close()
        if len(ts_sublist) == 1:
            # KLUDGEY case when only 1 row
            elem_list = ts_ndarray.tolist()
            ts_ndarray = {}
            for i, col_name in enumerate(ts_col_names):
                ts_ndarray[col_name] = numpy.array([elem_list[i]])
        return ts_ndarray


    def parse_asas_ts_data_str(self, ts_str):
        """ Custom timeseries string parser for ASAS timeseries data
        """
        out_dict = {}

        #   ^#ndata  ...header... 'GRADE FRAME'  ...timeseries...

        lines = ts_str.split('\n')
        in_header = False
        in_ts = False

        for line in lines:
            #if '2122.75720 12.537' in line:
            #    import pdb; pdb.set_trace()
            #    print
            ###This worked for ACVS but not fullcatalog:
            #if line[:6] == '#ndata':
            if line[:6] == '#ndata':
                continue # skip this since we calculate it later in the current version
            if line[:9] == '#dataset=':
                ###then we begin a header section
                if in_ts:
                    ### First we store parsed timeseries and associated header
                    if len(ts_sublist) == 0:
                        pass
                    elif (len(ts_sublist) == 1) and (len(ts_sublist[0]) == 0):
                        pass
                    else:
                        try:
                            dataset_name = header_dict['dataset']
                            out_dict[dataset_name] = header_dict
                            out_dict[dataset_name]['ts_ndarray'] = self.get_sub_ts_ndarray(ts_sublist, ts_col_names=ts_col_names)
                            out_dict[dataset_name]['ndata'] = len(ts_sublist)#len(out_dict[dataset_name]['ts_ndarray'])
                        except:
                            pass
                in_header = True
                in_ts = False
                header_dict = {'ndata':None, ####This worked for ACVS but not fullcatalog:#int(line.split()[1]),
                               'cmer_tups':[],
                               'cmag_dict':{},
                               'cmer_dict':{},
                               'dataset':line[10:]}
                continue
            if in_header:
                #if line[:8] == '#dataset':
                #    header_dict['dataset'] = line[10:]
                #    continue
                if line[:5] == '#cra=':
                    header_dict['ra'] = float(line[7:17]) * 15.0 # since Dotastro, TUTOR, and other code expects this to be degrees (currently the ASAS files have max(ra)==23.999)
                    continue
                elif line[:6] == '#cdec=':
                    header_dict['dec'] = float(line[7:17])
                    continue
                elif line[:5] == '#cmag':
                    header_dict['cmag_dict'][line[1:7]] = float(line.split()[1])
                    continue
                elif line[:5] == '#cmer':
                    cmer_name = line[1:7]
                    cmer_val = float(line.split()[1])
                    header_dict['cmer_dict'][cmer_name] = cmer_val
                    header_dict['cmer_tups'].append((cmer_val,cmer_name))
                    continue
                elif 'GRADE FRAME' in line:
                    ### We just finished parsing the header
                    in_header = False
                    in_ts = True
                    ts_sublist = []
                    ts_col_names = line[1:].split()
                    continue
            elif in_ts:
                ts_sublist.append(line)
        if in_ts:
            ### Finally, we store parsed timeseries and associated header
            if len(ts_sublist) == 0:
                pass
            elif (len(ts_sublist) == 1) and (len(ts_sublist[0]) == 0):
                pass
            else:
                try:
                    dataset_name = header_dict['dataset']
                    out_dict[dataset_name] = header_dict
                    out_dict[dataset_name]['ts_ndarray'] = self.get_sub_ts_ndarray(ts_sublist, ts_col_names=ts_col_names)
                    out_dict[dataset_name]['ndata'] = len(ts_sublist) #len(out_dict[dataset_name]['ts_ndarray'])
                except:
                    print("EXCEPT: calling self.get_sub_ts_ndarray(ts_sublist, ts_col_names)")
        return out_dict


    def add_aperture_mag_debug_info(self, aperture_mag_debug_dict={},
                                    source_intermed_dict={}):
        """ To be used to extract mag/aperture info from a source,
        which will later be used to find mag(aperture) relation.

        For a source, this finds the 'field/section' which has the most number of epochs,
        then, this finds the aperture with the minimum stddev in magnitude
        and then appends the chosen aperture and average magnitude.

        This information will then be used for determining the mag vs aperture relation.
    
        """
        #import pdb; pdb.set_trace()
        #print
        ndata_mstd_aperture_tups = []
        for d_name, d_dict in source_intermed_dict.iteritems():
            valid_inds = []
            if d_dict['ts_ndarray']['GRADE'].size == 1:
                #if ((d_dict['ts_ndarray']['GRADE'] == 'A')):
                if ((d_dict['ts_ndarray']['GRADE'] == 'A') or
                    (d_dict['ts_ndarray']['GRADE'] == 'B')):
                    valid_inds.append(0)
            else:
                valid_inds.extend(list(numpy.where((d_dict['ts_ndarray']['GRADE'] == 'A'))[0]))
                valid_inds.extend(list(numpy.where((d_dict['ts_ndarray']['GRADE'] == 'B'))[0]))
            valid_inds = numpy.array(valid_inds)
            if len(valid_inds) == 0:
                continue # nothing to use
            aperture_tups = []
            for mag_name in ['MAG_0', 'MAG_1', 'MAG_2', 'MAG_3', 'MAG_4']:
                if len(valid_inds) == 1:
                    try:
                        mag_avg = numpy.average(d_dict['ts_ndarray'][mag_name][valid_inds[0]])
                        mag_std = numpy.std(d_dict['ts_ndarray'][mag_name][valid_inds[0]])
                    except:
                        # we get here if d_dict['ts_ndarray'][mag_name] is a single scalar (not testable)
                        mag_avg = numpy.average(d_dict['ts_ndarray'][mag_name])
                        mag_std = numpy.std(d_dict['ts_ndarray'][mag_name])
                else:
                    mag_avg = numpy.average(d_dict['ts_ndarray'][mag_name][valid_inds])
                    mag_std = numpy.std(d_dict['ts_ndarray'][mag_name][valid_inds])
                    
                cmer_name = "cmer_%s" % (mag_name[-1])
                cmag_name = "cmag_%s" % (mag_name[-1])
                ### So, we choose the aperture which has the smallest mag_std (ignore 'cmer')
                aperture_tups.append((mag_std,mag_avg,mag_name))
            aperture_tups.sort() # minimum std is [0]
            
            ndata_mstd_aperture_tups.append((d_dict['ndata'],aperture_tups[0][1],aperture_tups[0][2]))
        ndata_mstd_aperture_tups.sort(reverse=True) # max n_epochs is [0]

        (final_ndata, final_mag, final_mag_name) = ndata_mstd_aperture_tups[0]

        aperture_mag_debug_dict['mag'].append(final_mag)
        aperture_mag_debug_dict['aperture'].append(int(final_mag_name[-1]))

        #print aperture_mag_debug_dict



    def filter_best_ts_aperture(self, intermed_dict):
        """ Using the intermediate dict from parse_asas_ts_data_str()
            - Choose the best aperture for each data frame/section
            - filter out low grade epochs

         Then return timeseries data in a form similar to Debosscher parse_ts_data()

        """
        ndata_mstd_aperture_tups = []
        field_aperture_avgmag_dict = {}
        field_aperture_data_dict = {}
        limitmag_dname_data_dict = {}
        for d_name, d_dict in intermed_dict.iteritems():
            #if d_name == "4 ; 2 F1840-24_233":
            #    import pdb; pdb.set_trace()
            #    print
            valid_inds = []
            c_nolim_inds = []
            c_lim_inds = []
            d_inds = []
            limit_mag_inds = (numpy.ndarray((0)),)
            if 'ts_ndarray' not in d_dict:
                continue # skip this d_name
            # # #
            #c_lim_inds = numpy.where(numpy.logical_and((d_dict['ts_ndarray']['MAG_0'] == 29.999), (d_dict['ts_ndarray']['GRADE'] == 'C')))
            #c_nolim_inds = numpy.where(numpy.logical_and((d_dict['ts_ndarray']['MAG_0'] != 29.999), (d_dict['ts_ndarray']['GRADE'] == 'C')))
            #d_inds = numpy.where(d_dict['ts_ndarray']['GRADE'] == 'D')
            # # #

            if d_dict['ts_ndarray']['GRADE'].size == 1:
                #if ((d_dict['ts_ndarray']['GRADE'] == 'A')):
                if ((d_dict['ts_ndarray']['GRADE'] == 'A') or
                    (d_dict['ts_ndarray']['GRADE'] == 'B')):
                    valid_inds.append(0)
                elif ((d_dict['ts_ndarray']['GRADE'] == 'C') and
                    (d_dict['ts_ndarray']['MAG_0'] == 29.999)):
                    c_lim_inds.append(0)
                elif ((d_dict['ts_ndarray']['GRADE'] == 'C')):
                    c_nolim_inds.append(0)
                elif ((d_dict['ts_ndarray']['GRADE'] == 'D')):
                    d_inds.append(0)
                ### In any case, there is no lim_mag GRADE==C, m29.999 when only 1 epoch
            else:
                c_lim_inds.extend(list(numpy.where(numpy.logical_and((d_dict['ts_ndarray']['MAG_0'] == 29.999), (d_dict['ts_ndarray']['GRADE'] == 'C')))[0]))
                c_nolim_inds.extend(list(numpy.where(numpy.logical_and((d_dict['ts_ndarray']['MAG_0'] != 29.999), (d_dict['ts_ndarray']['GRADE'] == 'C')))[0]))
                d_inds.extend(list(numpy.where(d_dict['ts_ndarray']['GRADE'] == 'D')[0]))


                valid_inds.extend(list(numpy.where((d_dict['ts_ndarray']['GRADE'] == 'A'))[0]))
                valid_inds.extend(list(numpy.where((d_dict['ts_ndarray']['GRADE'] == 'B'))[0]))
                # # # # # # 2012-11-26: dstarr adds both C & D flags for Kepler/ASAS (Northern ASAS survey):
                #import pdb; pdb.set_trace()
                #print

                #valid_inds.extend(list(numpy.where(numpy.logical_and((d_dict['ts_ndarray']['MAG_0'] < 29.9), (d_dict['ts_ndarray']['GRADE'] == 'C')))[0]))
                valid_inds.extend(numpy.where(numpy.logical_and(numpy.logical_and((d_dict['ts_ndarray']['MAG_0'] < 29.9),(d_dict['ts_ndarray']['GRADE'] == 'C')),(d_dict['ts_ndarray']['MAG_4'] < 29.9)))[0])
                valid_inds.extend(numpy.where(numpy.logical_and(numpy.logical_and((d_dict['ts_ndarray']['MAG_0'] < 29.9),(d_dict['ts_ndarray']['GRADE'] == 'D')),(d_dict['ts_ndarray']['MAG_4'] < 29.9)))[0])
                # # # # # #
                limit_mag_inds = numpy.where(numpy.logical_and((d_dict['ts_ndarray']['MAG_0'] == 29.999), (d_dict['ts_ndarray']['GRADE'] == 'C')))
                if len(limit_mag_inds[0]) > 0:
                    ### Then we need to retrieve the limiting mags for these sources and use these
                    ###   - these d_dict['ts_ndarray']['FRAME'][:10]  frame_ids
                    #   limit_mag_list = self.get_limit_mags(frame_id_list)
                    #   - actually I need to add these inds, mags to a seperate structure since not orig mags
                    #   - or, I need to replace existing mags for these inds with the retrieved limiting-mags(frame)
                    # - these limit_mags need to be seperate, so we can mark them seperately when inserting into
                    #     RDB table
                    for ind in limit_mag_inds[0]:
                        frame_name = d_dict['ts_ndarray']['FRAME'][ind]
                        if frame_name in self.frame_limitmags:
                            d_dict['ts_ndarray']['MAG_0'][ind] = self.frame_limitmags[frame_name]
                            d_dict['ts_ndarray']['MER_0'][ind] = 0.1 # TODO: have similar dict for errors: self.frame_limitmags[frame_name]
                        else:
                            ### The following places ibsdata_val=22 for upper limits for frames that have no calculated limit mag
                            ###    - currently limit mag is: m_p95 FROM asas_fullcat_frame_limits WHERE n >= 20.

                            d_dict['ts_ndarray']['MAG_0'][ind] = 22.0 # Rather than 29.9999, this is more plotable and is also larger than the largest A/B mag (21.584999)
                            d_dict['ts_ndarray']['MER_0'][ind] = 0.0 # TODO: have similar dict for errors: self.frame_limitmags[frame_name]
                    
                # # # # # # # # # # # # # # #print "limit_mags for d_name=", d_name, ':::', d_dict['ts_ndarray']['MAG_0'][limit_mag_inds]
                


            valid_inds = numpy.array(valid_inds)
            if len(valid_inds) == 0:
                continue # nothing to use
            aperture_tups = []
            field_aperture_avgmag_dict[d_name] = {}
            field_aperture_data_dict[d_name] = {}
            limitmag_dname_data_dict[d_name] = {'t':[],
                                                'm':[],
                                                'merr':[]}
            if len(limit_mag_inds[0]) > 0:
                # ???? should I caste the following as list()?:
                limitmag_dname_data_dict[d_name]['t'] = d_dict['ts_ndarray']['HJD'][limit_mag_inds]
                limitmag_dname_data_dict[d_name]['m'] = d_dict['ts_ndarray']['MAG_0'][limit_mag_inds]
                limitmag_dname_data_dict[d_name]['merr'] = d_dict['ts_ndarray']['MER_0'][limit_mag_inds]
            #else:
            #    ### what do I do?  Do I get here?
            #    import pdb; pdb.set_trace()
            #    print 

            for mag_name in ['MAG_0', 'MAG_1', 'MAG_2', 'MAG_3', 'MAG_4']:
                field_aperture_data_dict[d_name][mag_name] = {'t':[], 'm':[], 'merr':[], 'frame':[],
                                                              'frame_c_lim':[], 'm_c_lim':[],
                                                              'frame_c_nolim':[], 'm_c_nolim':[],
                                                              'frame_d':[], 'm_d':[],
                                                              }
                # # #
                if len(c_lim_inds) == 1:
                    try:
                        field_aperture_data_dict[d_name][mag_name]['frame_c_lim'].append(d_dict['ts_ndarray']['FRAME'][c_lim_inds[0]])
                        field_aperture_data_dict[d_name][mag_name]['m_c_lim'].append(d_dict['ts_ndarray'][mag_name][c_lim_inds[0]])
                        #import pdb; pdb.set_trace()
                        #print
                    except:
                        #we get here if it is a single scalar
                        field_aperture_data_dict[d_name][mag_name]['frame_c_lim'].append(d_dict['ts_ndarray']['FRAME'])
                        field_aperture_data_dict[d_name][mag_name]['m_c_lim'].append(d_dict['ts_ndarray'][mag_name])
                        #import pdb; pdb.set_trace()
                        #print
                elif len(c_lim_inds) > 1:
                    field_aperture_data_dict[d_name][mag_name]['frame_c_lim'] = d_dict['ts_ndarray']['FRAME'][c_lim_inds]
                    field_aperture_data_dict[d_name][mag_name]['m_c_lim'] = d_dict['ts_ndarray'][mag_name][c_lim_inds]
                    #import pdb; pdb.set_trace()
                    #print

                if len(c_nolim_inds) == 1:
                    try:
                        field_aperture_data_dict[d_name][mag_name]['frame_c_nolim'].append(d_dict['ts_ndarray']['FRAME'][c_nolim_inds[0]])
                        field_aperture_data_dict[d_name][mag_name]['m_c_nolim'].append(d_dict['ts_ndarray'][mag_name][c_nolim_inds[0]])
                    except:
                        #we get here if it is a single scalar
                        field_aperture_data_dict[d_name][mag_name]['frame_c_nolim'].append(d_dict['ts_ndarray']['FRAME'])
                        field_aperture_data_dict[d_name][mag_name]['m_c_nolim'].append(d_dict['ts_ndarray'][mag_name])
                elif len(c_nolim_inds) > 1:
                    field_aperture_data_dict[d_name][mag_name]['frame_c_nolim'] = d_dict['ts_ndarray']['FRAME'][c_nolim_inds]
                    field_aperture_data_dict[d_name][mag_name]['m_c_nolim'] = d_dict['ts_ndarray'][mag_name][c_nolim_inds]
                    
                if len(d_inds) == 1:
                    try:
                        field_aperture_data_dict[d_name][mag_name]['frame_d'].append(d_dict['ts_ndarray']['FRAME'][d_inds[0]])
                        field_aperture_data_dict[d_name][mag_name]['m_d'].append(d_dict['ts_ndarray'][mag_name][d_inds[0]])
                    except:
                        #we get here if it is a single scalar
                        field_aperture_data_dict[d_name][mag_name]['frame_d'].append(d_dict['ts_ndarray']['FRAME'])
                        field_aperture_data_dict[d_name][mag_name]['m_d'].append(d_dict['ts_ndarray'][mag_name])
                elif len(d_inds) > 1:
                    field_aperture_data_dict[d_name][mag_name]['frame_d'] = d_dict['ts_ndarray']['FRAME'][d_inds]
                    field_aperture_data_dict[d_name][mag_name]['m_d'] = d_dict['ts_ndarray'][mag_name][d_inds]
                    
                # # #
                if len(valid_inds) == 1:
                    try:
                        mag_avg = numpy.average(d_dict['ts_ndarray'][mag_name][valid_inds[0]])
                        field_aperture_data_dict[d_name][mag_name]['m'].append(d_dict['ts_ndarray'][mag_name][valid_inds[0]])
                        field_aperture_data_dict[d_name][mag_name]['t'].append(d_dict['ts_ndarray']['HJD'][valid_inds[0]])
                        field_aperture_data_dict[d_name][mag_name]['merr'].append(d_dict['ts_ndarray']["MER_%s" % (mag_name[-1])][valid_inds[0]])
                        field_aperture_data_dict[d_name][mag_name]['frame'].append(d_dict['ts_ndarray']['FRAME'][valid_inds[0]])
                    except:
                        ### we get here if d_dict['ts_ndarray'][mag_name] is a single scalar (not testable)
                        mag_avg = numpy.average(d_dict['ts_ndarray'][mag_name])
                        field_aperture_data_dict[d_name][mag_name]['m'].append(d_dict['ts_ndarray'][mag_name])
                        field_aperture_data_dict[d_name][mag_name]['t'].append(d_dict['ts_ndarray']['HJD'])
                        field_aperture_data_dict[d_name][mag_name]['merr'].append(d_dict['ts_ndarray']["MER_%s" % (mag_name[-1])])
                        field_aperture_data_dict[d_name][mag_name]['frame'].append(d_dict['ts_ndarray']['FRAME'])
                else:
                    mag_avg = numpy.average(d_dict['ts_ndarray'][mag_name][valid_inds])
                    field_aperture_data_dict[d_name][mag_name]['m'] = d_dict['ts_ndarray'][mag_name][valid_inds]
                    field_aperture_data_dict[d_name][mag_name]['t'] = d_dict['ts_ndarray']['HJD'][valid_inds]
                    field_aperture_data_dict[d_name][mag_name]['merr'] = d_dict['ts_ndarray']["MER_%s" % (mag_name[-1])][valid_inds]
                    field_aperture_data_dict[d_name][mag_name]['frame'] = d_dict['ts_ndarray']['FRAME'][valid_inds]
                ### Apparently we now use manx(npoints), not this: ### So, we choose the aperture which has the smallest mag_std (ignore 'cmer')
                field_aperture_avgmag_dict[d_name][int(mag_name[-1])] = mag_avg
            
            ndata_mstd_aperture_tups.append((d_dict['ndata'], d_name))
        ndata_mstd_aperture_tups.sort(reverse=True) # max n_epochs is [0]

        if len(ndata_mstd_aperture_tups) == 0:
            return {}
        (final_ndata, final_dname) = ndata_mstd_aperture_tups[0]
        # so final dict is: field_aperture_avgmag_dict[final_dname]
        # now need to find the median
        mag_median = numpy.median(field_aperture_avgmag_dict[final_dname].values())


        ### determine aperture:
        #poly = [4.95091422e-02,  -2.56105010e+00,   4.95802172e+01,  -4.26906532e+02, 1.38320479e+03]
        #x = mag_median
        #aperture_float = poly[0]*x*x*x*x + poly[1]*x*x*x + poly[2]*x*x + poly[3]*x + poly[4]
        #if aperture_float >= 3.5:
        #    aperture_int = 4
        #elif aperture_float >= 2.5:
        #    aperture_int = 3
        #elif aperture_float >= 1.5:
        #    aperture_int = 2
        #elif aperture_float >= 0.5:
        #    aperture_int = 1
        #else:
        #    aperture_int = 0

        ### 20120216: we get the following cuts from plot_aperture_mag_relation()'s m_lim_? values:
        # # # 20120619 (original, MACC-catalog apertures):
        if mag_median > 12.2795:
            aperture_int = 0
        elif mag_median > 11.6711:
            aperture_int = 1
        elif mag_median > 10.6547:
            aperture_int = 2
        else:
            aperture_int = 4
            
        # # # 1 size smaller aperture:
        #if mag_median > 11.6711:
        #    aperture_int = 0
        #elif mag_median > 10.6547:
        #    aperture_int = 1
        #else:
        #    aperture_int = 2 # NO: 3
        
        # # # 1 size larger aperture:
        #if mag_median > 12.2795:
        #    aperture_int = 1
        #elif mag_median > 11.6711:
        #    aperture_int = 2
        #elif mag_median > 10.6547:
        #    aperture_int = 4
        #else:
        #    aperture_int = 4

        ### Now get the timeseries for the chosen aperture

        mag_name = "MAG_%d" % (aperture_int)
        #print mag_median, aperture_float, mag_name
        t_final = []
        m_final = []
        merr_final = []
        ### The problem with this method is that there are sometimes duplicate times
        ### which are taken from different cameras and which will give error when inserting
        ### into TUTOR's tutor.obs_data table which has a primary key of (obs_id,time)
        #for d_name, d_dict in field_aperture_data_dict.iteritems():
        #    t_final.extend(d_dict[mag_name]['t'])
        #    m_final.extend(d_dict[mag_name]['m'])
        #    merr_final.extend(d_dict[mag_name]['merr'])

        ### So, instead, I do a cpu intense check for duplicates.  Note that I don't
        ###    do any sort of magnitude averaging if both the merr and time are the same
        ###   - I just randomly choose one m(t)
        frame_mag_dict = {}
        frame_c_lim_mag_dict = {}
        frame_c_nolim_mag_dict = {}
        frame_d_mag_dict = {}
        for d_name, d_dict in field_aperture_data_dict.iteritems():
            for i, frame in enumerate(d_dict[mag_name]['frame_c_lim']):
                frame_c_lim_mag_dict[frame] = d_dict[mag_name]['m_c_lim'][i]
            for i, frame in enumerate(d_dict[mag_name]['frame_c_nolim']):
                frame_c_nolim_mag_dict[frame] = d_dict[mag_name]['m_c_nolim'][i]
            for i, frame in enumerate(d_dict[mag_name]['frame_d']):
                frame_d_mag_dict[frame] = d_dict[mag_name]['m_d'][i]
            
            for i, t in enumerate(d_dict[mag_name]['t']):
                frame_mag_dict[int(d_dict[mag_name]['frame'][i])] = float(d_dict[mag_name]['m'][i])
                if t in t_final:
                    i_final = t_final.index(t)
                    if d_dict[mag_name]['merr'][i] < merr_final[i_final]:
                        del t_final[i_final]
                        del m_final[i_final]
                        del merr_final[i_final]
                        t_final.append(d_dict[mag_name]['t'][i])
                        m_final.append(d_dict[mag_name]['m'][i])
                        merr_final.append(d_dict[mag_name]['merr'][i])
                    elif ((d_dict[mag_name]['merr'][i] == merr_final[i_final]) and
                          (d_name == final_dname)):
                        ### The merrs, time, aperture are the same, but this case is in the more time-sampled data-group (presumably more central field/FOV).
                        del t_final[i_final]
                        del m_final[i_final]
                        del merr_final[i_final]
                        t_final.append(d_dict[mag_name]['t'][i])
                        m_final.append(d_dict[mag_name]['m'][i])
                        merr_final.append(d_dict[mag_name]['merr'][i])
                    # otherwise merr is larger and thus don't insert
                else:
                    t_final.append(d_dict[mag_name]['t'][i])
                    m_final.append(d_dict[mag_name]['m'][i])
                    merr_final.append(d_dict[mag_name]['merr'][i])
        print(mag_name, ':::', final_dname)

        return {'t':t_final,
                'm':m_final,
                'merr':merr_final,
                'aperture_num':aperture_int,
                'ra':intermed_dict[final_dname]['ra'],
                'dec':intermed_dict[final_dname]['dec'],
                'lim_m':limitmag_dname_data_dict[final_dname]['m'],
                'lim_t':limitmag_dname_data_dict[final_dname]['t'],
                'lim_merr':limitmag_dname_data_dict[final_dname]['merr'],
                'frame_mag_dict':frame_mag_dict,
                'frame_c_lim_mag_dict':frame_c_lim_mag_dict,
                'frame_c_nolim_mag_dict':frame_c_nolim_mag_dict,
                'frame_d_mag_dict':frame_d_mag_dict,
                }


    def plot_aperture_mag_relation(self, aperture_list=[], mag_list=[], n_src_plot_cut=0,
                                   generate_aperture_hist_plot=False):
        """ Generate a plot intended for determining the mag(aperture) relation.
        Print out the parameters from several polynomial fits, one which
        will be used to model the relation and thus be used to select an aperture
        depending upon average magnitude.
    
        """
        import matplotlib.pyplot as pyplot
        from matplotlib import rcParams
        aperture = numpy.array(aperture_list)
        mag = numpy.array(mag_list)
        stat_aper = [4,3,2,1,0] #[-2,-1,2,1,0,4,3] # [-2,-1] + range(5)
        stat_mag_avg = [14.9, 13.75]
        stat_mag_std = [0, 0]
        if generate_aperture_hist_plot:
            rcParams.update({'legend.fontsize':8})
            fig = pyplot.figure()
            ax = fig.add_subplot('111')
            from scipy.stats import norm  # for debug plotting
            color_list = ['m','r','y','g','b']
        hist_aper_n_per_bin = {}
        for aper_val in stat_aper:#[2:]:
            aper_inds = numpy.where(aperture == aper_val)
            # NOTE: currently the aperture ording is in reverse, should allow arbitrary order
            ###
            if generate_aperture_hist_plot:
                mags = mag[aper_inds]
                #fits = norm.fit(mags)
                #dist = norm(fits)
                probs = []
                #for m in mags:
                #    probs.append(dist.pdf(m)[0]  * len(mag[aper_inds])/float(len(mag)))
                n, bins, patches = pyplot.hist(mags, bins=70, normed=False, facecolor=color_list[aper_val],
                            alpha=0.6, label='%d pixel, %d" aperture' % (aper_val + 2, 15*(aper_val + 2)),
                                               range=(6,15))
                hist_aper_n_per_bin[aper_val] = n
                print('aper, max(n)', aper_val, max(n))
                #pyplot.plot(mags, probs, color_list[aper_val] + 'o', ms=3)
            ##
            # obsolete# stat_mag_avg.append(numpy.average(mag[aper_inds]))
            # obsolete# stat_mag_std.append(numpy.std(mag[aper_inds]))                
        if generate_aperture_hist_plot:
            import scipy.stats as stats

            de_mags0 = stats.gaussian_kde(mag[numpy.where(aperture == 0)])
            de_mags1 = stats.gaussian_kde(mag[numpy.where(aperture == 1)])
            de_mags2 = stats.gaussian_kde(mag[numpy.where(aperture == 2)])
            de_mags3 = stats.gaussian_kde(mag[numpy.where(aperture == 3)])
            de_mags4 = stats.gaussian_kde(mag[numpy.where(aperture == 4)])
            n_mag0 = len(mag[numpy.where(aperture == 0)])
            n_mag1 = len(mag[numpy.where(aperture == 1)])
            n_mag2 = len(mag[numpy.where(aperture == 2)])
            n_mag3 = len(mag[numpy.where(aperture == 3)])
            n_mag4 = len(mag[numpy.where(aperture == 4)])
            mag_vec = numpy.arange(6,16,0.0001) #0.01

            ### These have maxima that do not scale to histograms (max is related to distribution shape)
            #pyplot.plot(mag_vec, de_mags0.evaluate(mag_vec)*n_mag0 * 0.15, 'm-',linewidth=2)
            #pyplot.plot(mag_vec, de_mags1.evaluate(mag_vec)*n_mag1 * 0.15, 'r-',linewidth=2)
            #pyplot.plot(mag_vec, de_mags2.evaluate(mag_vec)*n_mag2 * 0.15, 'y-',linewidth=2)
            #pyplot.plot(mag_vec, de_mags3.evaluate(mag_vec)*n_mag3 * 0.15, 'g-',linewidth=2)
            #pyplot.plot(mag_vec, de_mags4.evaluate(mag_vec)*n_mag4 * 0.15, 'b-',linewidth=2)
            
            def which_aper(m):
                denest_prior_4 = de_mags4.evaluate(m)*n_mag4
                a = [((de_mags0.evaluate(m)*n_mag0)/(denest_prior_4), 0),
                     ((de_mags1.evaluate(m)*n_mag1)/(denest_prior_4), 1),
                     ((de_mags2.evaluate(m)*n_mag2)/(denest_prior_4), 2),
                     ((de_mags3.evaluate(m)*n_mag3)/(denest_prior_4), 3),
                     (1,4)]
                a.sort(reverse=True)
                return a[0][1]

            apers_vec = numpy.array([which_aper(x) for x in mag_vec])
            asas_new_apers = numpy.array([which_aper(x) for x in mag]) # this takes a very long time (5-10 mins?)
            #m_lim_0 = mag_vec[max(numpy.where(apers_vec==0)[0])]
            #m_lim_1 = mag_vec[max(numpy.where(apers_vec==1)[0])]
            #m_lim_2 = mag_vec[max(numpy.where(apers_vec==2)[0])]
            ##m_lim_3 = mag_vec[max(numpy.where(apers_vec==3)[0])]  # Aperture dist is below all others
            #m_lim_4 = mag_vec[max(numpy.where(apers_vec==4)[0])]

            m_lim_0 = max(mag_vec[numpy.where(apers_vec==0)])
            m_lim_1 = max(mag_vec[numpy.where(apers_vec==1)])
            m_lim_2 = max(mag_vec[numpy.where(apers_vec==2)])
            m_lim_4 = max(mag_vec[numpy.where(apers_vec==4)])
            print('mag_vec: m_lim_0,1,2,4:', m_lim_0, m_lim_1, m_lim_2, m_lim_4)

            m_lim_0 = max(mag[numpy.where(asas_new_apers==0)])
            m_lim_1 = max(mag[numpy.where(asas_new_apers==1)])
            m_lim_2 = max(mag[numpy.where(asas_new_apers==2)])
            m_lim_4 = max(mag[numpy.where(asas_new_apers==4)])

            print('mag: m_lim_0,1,2,4:', m_lim_0, m_lim_1, m_lim_2, m_lim_4)

            # TODO: need to get all True values, not just len()
            print('orig std min chosen apertures:', n_mag0, n_mag1, n_mag2, n_mag3, n_mag4)
            print('len(numpy.where(asas_new_apers==0)[0])', \
                  len(numpy.where(asas_new_apers==0)[0]), \
                  len(numpy.where(asas_new_apers==1)[0]), \
                  len(numpy.where(asas_new_apers==2)[0]), \
                  len(numpy.where(asas_new_apers==3)[0]), \
                  len(numpy.where(asas_new_apers==4)[0]))
            print('on aperture 3 point: ', mag[numpy.where(asas_new_apers==3)])
            #import pdb; pdb.set_trace()
            #print

            #pyplot.plot([m_lim_0, m_lim_0], [0,1400], 'k-')
            pyplot.plot([m_lim_1, m_lim_1], [0,1400], 'k-')
            pyplot.plot([m_lim_2, m_lim_2], [0,1400], 'k-')
            pyplot.plot([m_lim_4, m_lim_4], [0,1400], 'k-')
            ax.annotate('2 pixel',xy=(m_lim_1 + 0.2, 1360), xycoords='data', 
                        horizontalalignment='left', verticalalignment='top', fontsize=8)
            ax.annotate(len(numpy.where(asas_new_apers==0)[0]),
                                 xy=(13.5, 1280), xycoords='data', 
                        horizontalalignment='left', verticalalignment='top', fontsize=8)
            ax.annotate('3 px', xy=(m_lim_2 + 0.07, 1360), xycoords='data', 
                        horizontalalignment='left', verticalalignment='top', fontsize=8)
            ax.annotate(len(numpy.where(asas_new_apers==1)[0]),
                                 xy=(m_lim_2 + 0.07, 1280), xycoords='data', 
                        horizontalalignment='left', verticalalignment='top', fontsize=8)
            ax.annotate('4 pixel', xy=(m_lim_4 + 0.1, 1360), xycoords='data', 
                        horizontalalignment='left', verticalalignment='top', fontsize=8)
            ax.annotate(len(numpy.where(asas_new_apers==2)[0]),
                                 xy=(m_lim_4 + 0.1, 1280), xycoords='data', 
                        horizontalalignment='left', verticalalignment='top', fontsize=8)
            #ax.annotate('5', xy=(10.6374 + 0.15, 0.76), xycoords='data', 
            #            horizontalalignment='left', verticalalignment='top', fontsize=8)
            ax.annotate('6 pixel', xy=(m_lim_4 - 0.85, 1360), xycoords='data', 
                        horizontalalignment='left', verticalalignment='top', fontsize=8)
            ax.annotate(len(numpy.where(asas_new_apers==4)[0]),
                                 xy=(m_lim_4 - 0.85, 1280), xycoords='data', 
                        horizontalalignment='left', verticalalignment='top', fontsize=8)

            ax.set_xlim(6, 15)
            #ax.set_ylim(0, 0.8)
            ax.set_xlabel("Source average magnitude")
            ax.set_ylabel("N of sources")
            ax.legend(loc=2)
            #fpath = os.path.expandvars('$HOME/scratch/asas_data/aperture_analysis_4.png')
            fpath = os.path.expandvars('$HOME/src/ASASCatalog/plots/asas_aperture.pdf')
            pyplot.savefig(fpath)
            ####os.system('xview %s &' % (fpath))
            #os.system('eog %s &' % (fpath))
            pyplot.show()
            pyplot.clf()

        ###
        """
        poly = numpy.polyfit(stat_mag_avg, stat_aper, 4)
        print '4 POLY:', poly
        x = numpy.arange(9, 15, 0.1)
        y = poly[0]*x*x*x*x + poly[1]*x*x*x + poly[2]*x*x + poly[3]*x + poly[4]
        pyplot.plot(y, x, 'mo-', ms=2) #color='green')

        ###
        poly = numpy.polyfit(stat_mag_avg, stat_aper, 3)
        print '3 POLY:', poly
        x = numpy.arange(9, 15, 0.1)
        y = poly[0]*x*x*x + poly[1]*x*x + poly[2]*x + poly[3]
        pyplot.plot(y, x, 'ko-', ms=2) #color='green')

        ###
        #poly = numpy.polyfit(stat_mag_avg, stat_aper, 2)
        #print '2 POLY:', poly
        #x = numpy.arange(9, 15, 0.1)
        #y = poly[0]*x*x + poly[1]*x + poly[2]
        #pyplot.plot(y, x, 'go-', ms=2) #color='green')

        ###
        poly = numpy.polyfit(stat_mag_avg, stat_aper, 1)
        print '1 POLY:', poly
        x = numpy.arange(9, 15, 0.1)
        y = poly[0]*x + poly[1]
        pyplot.plot(y, x, 'bo-', ms=2) #color='green')

        #pyplot.plot(aperture, mag, 'bo', ms=2)
        pyplot.errorbar(stat_aper, stat_mag_avg, yerr=stat_mag_std, marker='x',
                        mfc='red', mec='red', ms=10, mew=1,
                        ecolor='red', elinewidth=1, color='red')
        
        #pyplot.xlim(-2, 5)
        #pyplot.ylim(9, 15)
        pyplot.xlim(-1, 5)
        pyplot.ylim(9, 14)
        #title_str = 'Vmag vs aperture %d Using A B' % (n_src_plot_cut)
        title_str = 'Vmag vs aperture x Using A B'# % (n_src_plot_cut)
        pyplot.title(title_str)
        fpath = "/tmp/asas_mag_aper_%s.ps" % (title_str.replace(' ','_'))
        pyplot.savefig(fpath)
        #os.system('gv %s &' % (fpath))
        pyplot.show()
        """
        # # # #
        # # # # NOTE: this is all assuming that the smallest std choice for the ideal aperture is best.  it might be better to choose???? some other feature of the scatter / timeseries?45sv
        #sys.exit()

        #### This HDF5 file can be read my IpyNotebook: acvs_aperture_analysis_20120208
        #import h5py
        #f = h5py.File('/Data/dstarr/Data/asas_ACVS_50k_data/aperture_plot_sanitycheck.hdf5', 'w') # 'a' is default if not specified
        #ds = f.create_dataset('aperture', data=aperture)
        #ds = f.create_dataset('mag', data=mag)
        #f.close()

    # OBSOLETE:
    def plot_aperture_mag_relation__backup(self, aperture_list=[], mag_list=[], n_src_plot_cut=0):
        """ Generate a plot intended for determining the mag(aperture) relation.
        Print out the parameters from several polynomial fits, one which
        will be used to model the relation and thus be used to select an aperture
        depending upon average magnitude.
    
        """
        import matplotlib.pyplot as pyplot
        aperture = numpy.array(aperture_list)
        mag = numpy.array(mag_list)

        stat_aper = [-2,-1] + range(5)
        stat_mag_avg = [14.9, 13.75]
        #CRAP#stat_mag_avg = [15.5, 14]
        stat_mag_std = [0, 0]
        for aper_val in stat_aper[2:]:
            aper_inds = numpy.where(aperture == aper_val)
            stat_mag_avg.append(numpy.average(mag[aper_inds]))
            stat_mag_std.append(numpy.std(mag[aper_inds]))

        ###
        poly = numpy.polyfit(stat_mag_avg, stat_aper, 4)
        print('4 POLY:', poly)
        x = numpy.arange(9, 15, 0.1)
        y = poly[0]*x*x*x*x + poly[1]*x*x*x + poly[2]*x*x + poly[3]*x + poly[4]
        pyplot.plot(y, x, 'mo-', ms=2) #color='green')

        ###
        poly = numpy.polyfit(stat_mag_avg, stat_aper, 3)
        print('3 POLY:', poly)
        x = numpy.arange(9, 15, 0.1)
        y = poly[0]*x*x*x + poly[1]*x*x + poly[2]*x + poly[3]
        pyplot.plot(y, x, 'ko-', ms=2) #color='green')

        ###
        #poly = numpy.polyfit(stat_mag_avg, stat_aper, 2)
        #print '2 POLY:', poly
        #x = numpy.arange(9, 15, 0.1)
        #y = poly[0]*x*x + poly[1]*x + poly[2]
        #pyplot.plot(y, x, 'go-', ms=2) #color='green')

        ###
        poly = numpy.polyfit(stat_mag_avg, stat_aper, 1)
        print('1 POLY:', poly)
        x = numpy.arange(9, 15, 0.1)
        y = poly[0]*x + poly[1]
        pyplot.plot(y, x, 'bo-', ms=2) #color='green')

        #pyplot.plot(aperture, mag, 'bo', ms=2)
        pyplot.errorbar(stat_aper, stat_mag_avg, yerr=stat_mag_std, marker='x',
                        mfc='red', mec='red', ms=10, mew=1,
                        ecolor='red', elinewidth=1, color='red')
        
        #pyplot.xlim(-2, 5)
        #pyplot.ylim(9, 15)
        pyplot.xlim(-1, 5)
        pyplot.ylim(9, 14)
        title_str = 'Vmag vs aperture %d Using A B' % (n_src_plot_cut)
        pyplot.title(title_str)
        fpath = "/tmp/asas_mag_aper_%s.ps" % (title_str.replace(' ','_'))
        pyplot.savefig(fpath)
        os.system('gv %s &' % (fpath))
        #pyplot.show()
        # # # #
        # # # # NOTE: this is all assuming that the smallest std choice for the ideal aperture is best.  it might be better to choose???? some other feature of the scatter / timeseries?45sv
        #sys.exit()


    def append_frameid_fmag_to_disk(self, frame_mag_dict={}):
        """ Just append to file the (frame_id, mag) information so that
        this can be imported into other databases.
         - I expect this to be a several GB file.
        """
        line_list = []
        for frame_id, f_mag in frame_mag_dict.iteritems():
            line_list.append("%d %f\n" % (frame_id, f_mag))
        fp = open('/home/pteluser/scratch/asas_fullcat_idmag.dat', 'a')
        fp.write(''.join(line_list) + '\n')
        fp.close()


    def update_frame_mag_tally(self, frame_mag_dict={},
                               frame_c_lim_mag_dict={},
                               frame_c_nolim_mag_dict={},
                               frame_d_mag_dict={}):
        """ Add given frame(mags) to running tally / metrics which will be used
        to determine limiting mags for each frame
               
        """
        if 0:
            # for teting of the online variance calculating algorithm
            import scipy
            a = scipy.random.random_sample((100))
            n = 0
            mean = 0
            variance = 0
            for x in a:
                (n, mean, variance) = calc_variance(x, n, mean, variance)
            print(n, mean, variance)

            print("len(a)=%d   mean=%f   var=%f" % (len(a), scipy.mean(a), scipy.var(a)))

        for frame_id in frame_c_lim_mag_dict.keys():
            self.frame_mag_tally['n_c_lim'][frame_id] += 1

        for frame_id in frame_c_nolim_mag_dict.keys():
            self.frame_mag_tally['n_c_nolim'][frame_id] += 1

        for frame_id in frame_d_mag_dict.keys():
            self.frame_mag_tally['n_d'][frame_id] += 1

        for frame_id, f_mag in frame_mag_dict.iteritems():
            (n, mean, variance) = calc_variance(f_mag,
                                                self.frame_mag_tally['n'][frame_id],
                                                self.frame_mag_tally['m_avg'][frame_id],
                                                self.frame_mag_tally['m_var'][frame_id])
            if n == 0:
                ### debug
                import pdb; pdb.set_trace()
                print()
            self.frame_mag_tally['n'][frame_id] = n
            self.frame_mag_tally['m_avg'][frame_id] = mean
            self.frame_mag_tally['m_var'][frame_id] = variance

            if f_mag > self.frame_mag_tally['m4'][frame_id]:
                ### then f_mag will atleast replace m4
                mags_sorted = numpy.sort([f_mag,
                                          self.frame_mag_tally['m4'][frame_id],
                                          self.frame_mag_tally['m3'][frame_id],
                                          self.frame_mag_tally['m2'][frame_id],
                                          self.frame_mag_tally['m1'][frame_id],
                                          self.frame_mag_tally['m0'][frame_id]],
                                         kind='mergesort') # %timeit says this is faster for this semi-sorted list

                self.frame_mag_tally['m4'][frame_id] = mags_sorted[1] # mags_sorted[0] is the smallest and thus brightest
                self.frame_mag_tally['m3'][frame_id] = mags_sorted[2] 
                self.frame_mag_tally['m2'][frame_id] = mags_sorted[3] 
                self.frame_mag_tally['m1'][frame_id] = mags_sorted[4] 
                self.frame_mag_tally['m0'][frame_id] = mags_sorted[5] # This is the largest, thus faintest
            

    def download_timeseries_datasets_from_web(self, source_dict={}, i_src_low=0, i_src_high=2,
                                              do_plot=True, do_generate_ts_source_data=True,
                                              do_update_frame_mag_table=False):
        """ Download the timeseries ASAS ACVS data from the web.

        Data retrieved from URLs like:
        http://www.astrouw.edu.pl/cgi-asas/asas_cgi_get_data?005924-1556.6,asas3
        http://www.astrouw.edu.pl/cgi-asas/asas_cgi_get_data?183627-3149.5,asas3
        """
        import urllib
        import matplotlib.pyplot as pyplot
        aperture_mag_debug_dict = {'mag':[], 'aperture':[]} # for debug / diagnostic use only
        source_data = {}
        for i_src, source_name in enumerate(source_dict['ID'][i_src_low:i_src_high]):
            #if source_name == '182649-3223.4':
            #    import pdb; pdb.set_trace()
            #    print
            #else:
            #    continue
            print('i_src::', i_src, end=' ')
            ts_fpath = "%s/%s" % (self.pars['asas_timeseries_dirpath'], source_name) # #ACVS 126:
            #proj=131 asas: ts_fpath = "%s/%s.dat" % (self.pars['asas_timeseries_dirpath'], source_name)
            #import pdb; pdb.set_trace()
            #print

            if os.path.exists(ts_fpath):
                ts_str = open(ts_fpath).read()
            else:
                url_str = "%s%s%s" % (self.pars['asas_url_prefix'], source_name,
                                      self.pars['asas_url_suffix'])
                f_url = urllib.urlopen(url_str)
                ts_str = f_url.read()
                f_url.close()
                f_disk = open(ts_fpath, 'w')
                f_disk.write(ts_str)
                f_disk.close()
            try:
                source_intermed_dict = self.parse_asas_ts_data_str(ts_str)
            except:
                ### If the ts-datafile/string has malformed header (random characters), we will skip it here.
                print("EXCEPT: Calling parse_asas_ts_data_str(ts_str)")
                source_intermed_dict = {}
            if do_plot:
                ##### For PLOTTING ONLY:
                self.add_aperture_mag_debug_info(aperture_mag_debug_dict=aperture_mag_debug_dict,
                                                 source_intermed_dict=source_intermed_dict)
                print(i_src, source_name, aperture_mag_debug_dict['aperture'][-1], aperture_mag_debug_dict['mag'][-1])
            ### probably no need to add source_data[source_name]['fname']
            if do_generate_ts_source_data:
                if len(source_intermed_dict) == 0:
                    continue # 20120103 added this skip
                source_data[source_name] = {'source_name':source_name,
                                            'ts_data':{'V':{}}}

                source_data[source_name]['ts_data']['V'] = self.filter_best_ts_aperture(source_intermed_dict)
                if len(source_data[source_name]['ts_data']['V']) == 0:
                    source_data.pop(source_name)
                    continue
                if do_update_frame_mag_table:
                    # # # now we want to incorperate source_data[source_name]['ts_data']['V']['frame_mag_dict']
                    #     to some tally dict
                    # - want to delete other data structures, and after adding, delete the ['frame_mag_dict'] dict
                    if 'frame_mag_dict' in source_data[source_name]['ts_data']['V']:
                        self.append_frameid_fmag_to_disk(frame_mag_dict=source_data[source_name]['ts_data']['V']['frame_mag_dict'])

                        self.update_frame_mag_tally(frame_mag_dict=source_data[source_name]['ts_data']['V']['frame_mag_dict'],
                                                    frame_c_lim_mag_dict=source_data[source_name]['ts_data']['V']['frame_c_lim_mag_dict'],
                                                    frame_c_nolim_mag_dict=source_data[source_name]['ts_data']['V']['frame_c_nolim_mag_dict'],
                                                    frame_d_mag_dict=source_data[source_name]['ts_data']['V']['frame_d_mag_dict'],
                                                    )
                    #del source_data[source_name]['ts_data']['V']['frame_mag_dict'] # done with this, allow gc
                    del source_data[source_name] # done with this, allow gc
                    #import pdb; pdb.set_trace()
                    #print
            ### For debugging (without running on whole dataset):
            #if i_src >= n_src_plot_cut:
            #    break # return and do plotting if specified

        if do_plot:
            self.plot_aperture_mag_relation(aperture_list=aperture_mag_debug_dict['aperture'],
                                            mag_list=aperture_mag_debug_dict['mag'],
                                            #n_src_plot_cut=n_src_plot_cut,
                                            generate_aperture_hist_plot=True)
            import pdb; pdb.set_trace()
        return source_data


    def make_better_source_file(self, source_dict={}, source_ts_dict={}, n_src_cut=0):
        """ Generate a new source file which has RA, Dec, and consistant classifications
        """
        # TODO: determine better classes
        # TODO: retrieve ra, dec from timeseries files

        asas_to_tutor_classes = { \
            'ACV':'aii',
            'BCEP':'bc',
            'CW':'piic',
            'CW-FO':'piic',
            'CW-FU':'piic',
            'DCEP':'dc',
            'DCEP-FO':'cm',
            'DCEP-FU':'dc',
            'DSCT':'ds',
            'EC':'wu',
            'ED':'d',
            'ESD':'sd',
            'ELL':'ell',
            'MIRA':'mira',
            'NOVA':'nov',
            'RRAB':'rr-ab',
            'RRC':'rr-c',
            'SR':'sreg'}

        asas_classes = asas_to_tutor_classes.keys()

        write_lines = []
        for i, asas_type in enumerate(source_dict['TYPE'][:n_src_cut+1]):
            if asas_type in asas_classes:
                limited_asas_class = asas_type
            else:
                limited_asas_class = ''
            tutor_class = asas_to_tutor_classes.get(limited_asas_class,'')
            source_name = source_dict['ID'][i]
            #print "%5d %s %20s\t%s\t%s\t%lf" % (i, source_name, asas_type, limited_asas_class, tutor_class, source_ts_dict[source_name]['ts_data']['V']['ra'])
            #print "%5d %s %5s %10lf %10lf" % (i, source_name, tutor_class, source_ts_dict[source_name]['ts_data']['V']['ra'], source_ts_dict[source_name]['ts_data']['V']['dec'])
            #LOOKS NICE BUT IS CONFUSING TO TUTOR IMPORT#write_lines.append("%5d %s %5s %10lf %10lf\n" % (i, source_name, tutor_class, source_ts_dict[source_name]['ts_data']['V']['ra'], source_ts_dict[source_name]['ts_data']['V']['dec']))
            write_lines.append("%d\t%s\t%5s\t%10lf\t%10lf\n" % (i, source_name, tutor_class, source_ts_dict[source_name]['ts_data']['V']['ra'], source_ts_dict[source_name]['ts_data']['V']['dec']))

            #ts_fpath = "%s/%s" % (self.pars['asas_timeseries_dirpath'], source_name)
            #if not os.path.exists(ts_fpath):
            #    print 'NO TS file:', i, ts_fpath
            #    continue # skip
            #lines = open(ts_fpath).readlines()
            #for line in lines:
        import pdb; pdb.set_trace()
        print()
        if os.path.exists(self.pars['new_source_tutoringest_fpath']):
            os.system ('rm ' + self.pars['new_source_tutoringest_fpath'])
        fp_out = open(self.pars['new_source_tutoringest_fpath'], 'w')
        fp_out.writelines(write_lines)
        fp_out.close()
        

        #'ID','PER','HJD0','VMAX','VAMP','TYPE','GCVS_ID','GCVS_TYPE',
        #'IR12','IR25','IR60','IR100','J','H','K',
        #'V_IR12','V_J','V_H','V_K','J_H','H_K'), \    


    def iband_source_comparison(self, source_dict={}):
        """ Compare which sources are available in I-band,
        which are also avaible in Vband ACVS group.
        """
        from numpy import loadtxt

        #:'/home/pteluser/scratch/asas_data/i_band/a2per',

        iband_per_ndarray = loadtxt(self.pars['source_data_iband_per_fpath'], comments='#',
                    dtype={'names':('ID','I-mag','Amp','Err','Period','Nobs','Fields','Cross-ID'), \
                           'formats':('S13','f8','f8','f8','f8','i8','S11','S11')})

        iband_misc_ndarray = loadtxt(self.pars['source_data_iband_misc_fpath'], comments='#',
                    dtype={'names':('ID','I-mag','Amp','Err','Nobs'), \
                           'formats':('S13','f8','f8','f8','i8')})

        i_count = 0
        for src_name in iband_per_ndarray['ID']:
            if src_name in source_dict['ID']:
                print('I per also in ACVS:', src_name)
                i_count += 1

        for src_name in iband_misc_ndarray['ID']:
            if src_name in source_dict['ID']:
                print('Imisc also in ACVS:', src_name)
                i_count += 1

        print('Count of ACVS matching sources:', i_count)
        import pdb; pdb.set_trace()

        #'source_data_iband_allsrc_fpath':'/home/pteluser/scratch/asas_data/i_band/asas2-cat',
        #'source_data_iband_misc_fpath':'/home/pteluser/scratch/asas_data/i_band/a2misc',



        pass
        

    def timeseries_main(self, write_source_file=False):
        """ Main tools for retrieving ASAS timeseries data and parsing the relevant TS data.
        """         
        if 1:
            ### ACVS asas source case: (proj 126) (50000 sources)
            source_dict = self.retrieve_parse_asas_acvs_source_data()
        if 0:
            ### General non-variable fullcatalog ASAS sources case: (proj 131) (20 Million sources)
            source_dict = self.retrieve_fullcatalog_source_dict()

        if 0:
            # This is not fully developed?
            self.iband_source_comparison(source_dict=source_dict)
            import pdb; pdb.set_trace()

        if 0:
            ### This is used when only plotting of existing timeseries files is needed.
            ###   - NOTE: this will check for a local copy of a timeseries before wget/urllib retrieve
            #n_src_plot_cut = 60000
            source_ts_dict = self.download_timeseries_datasets_from_web( \
                                          source_dict=source_dict,
                                          i_src_low=0,
                                          i_src_high=60000,
                                          do_plot=True,
                                          do_generate_ts_source_data=False)
        if 1:
            ### This condition is used when all 50k timeseries files are available and a new 
            ###       source file needs to be generated.
            print("starting loop")

            self.retrieve_fullcat_frame_limitmags()

            ### When inserting source timeseries into the TUTOR tables:
            n_max = len(source_dict['ID']) #4=testing #len(source_dict['ID'])
            num_n_for_insert = 60000 # 1000 #2=testing # 10000= for filling asas_fullcat_frame_limits table
            do_update_frame_mag_table=False #True # to only be used when filling the asas_fullcat_frame_limits table
            
            ### When re-populating the asas_fullcat_frame_limits TABLE:
            #n_max = len(source_dict['ID'])
            #num_n_for_insert = 10000 # 10000= for filling asas_fullcat_frame_limits table
            #do_update_frame_mag_table=True # to only be used when filling the asas_fullcat_frame_limits table

            if do_update_frame_mag_table:
                self.initialize_frame_mag_tally_dict() 
            for i_low in range(0, n_max, num_n_for_insert):
                print('i_low', i_low, n_max)
                i_src_low = i_low
                i_src_high = i_low + num_n_for_insert
                source_ts_dict = self.download_timeseries_datasets_from_web( \
                                              source_dict=source_dict,
                                              i_src_low=i_src_low,
                                              i_src_high=i_src_high,
                                              do_plot=False,
                                              do_generate_ts_source_data=True,
                                              do_update_frame_mag_table=do_update_frame_mag_table)
                if do_update_frame_mag_table:
                    self.update_frame_mag_tally_table()

                #import pdb; pdb.set_trace()
                #print
                if write_source_file:
                    ### Generate a new source file which has RA, Dec, and consistant classifications
                    self.make_better_source_file(source_dict=source_dict,
                                                 source_ts_dict=source_ts_dict,
                                                 n_src_cut=i_src_high - i_src_low - 1)

                if not do_update_frame_mag_table:
                    ### insert timeseries into database:
                    if len(source_ts_dict) == 0:
                        continue # I find that this occurs for: (i_src_low, i_src_high) = (634000 635000)
                    Timeseries_Insert = TimeseriesInsert(pars=self.pars)
                    Timeseries_Insert.main(source_data=source_ts_dict)
            


        ### Pickling is not efficient.  Takes too long to write/read, as opposed to just
        ###       generating the source_ts_dict on the file
        #import cPickle
        #import gzip
        #print 'Pickling...'
        #if os.path.exists(self.pars['aper_chosen_sources_pkl_fpath']):
        #    os.system('rm ' + self.pars['aper_chosen_sources_pkl_fpath'])
        #fp = gzip.open(self.pars['aper_chosen_sources_pkl_fpath'],'wb')
        #cPickle.dump(source_ts_dict,fp,cPickle.HIGHEST_PROTOCOL) # ,1) means a binary pkl is used.
        #fp.close()
        #print 'Pickling DONE.'
        
        import pdb; pdb.set_trace()
        print()

        ### TODO: ingest the ASAS source file into TUTOR using web interface.



        ### TODO: need to match with TUTOR sources using source_name:
        #sourceid_lookup = self.query_sourcename_sourceid_lookup(project_id=self.pars['project_id'])
        #self.update_with_sourceids(sourceid_lookup=sourceid_lookup, source_data=source_data)
        #self.insert_into_observations_table(debug=True, source_data=source_data, ....)


if __name__ == '__main__':
    sys.excepthook = invoke_pdb




    pars = { \
        'user_id':3, # 3 = dstarr in tutor.users
        #'tcptutor_hostname':'127.0.0.1',
        #'tcptutor_username':'dstarr', # guest
        #'tcptutor_password':'ilove2mass', #'iamaguest',
        #'tcptutor_database':'tutor_with_limitmags',
        #'tcptutor_port':3306,

        'tcptutor_hostname':'192.168.1.103',
        'tcptutor_username':'dstarr', # guest
        'tcptutor_password':'ilove2mass', #'iamaguest',
        'tcptutor_database':'tutor',
        'tcptutor_port':3306,

        'tcp_hostname':'192.168.1.25',
        'tcp_username':'pteluser',
        'tcp_port':     3306, #23306, 
        'tcp_database':'source_test_db',
        }

    user_path = '/home/dstarr'; #'/home/pteluser'
    asas_pars = { \
        'source_data_fpath':user_path  +'/scratch/asas_data/ACVS.1.1',
        'source_data_iband_allsrc_fpath':user_path  +'/scratch/asas_data/i_band/asas2-cat',
        'source_data_iband_misc_fpath':user_path  +'/scratch/asas_data/i_band/a2misc',
        'source_data_iband_per_fpath':user_path  +'/scratch/asas_data/i_band/a2per',
        'new_source_tutoringest_fpath':user_path  +'/scratch/asas_data/new_fortutor_ACVS.1.1', #user_path  +'/scratch/asas_data/new_fortutor_ASAS_fullcat',#'/home/pteluser/scratch/asas_data/new_fortutor_ACVS.1.1',
        #'aper_chosen_sources_pkl_fpath':'/home/pteluser/scratch/asas_data/aper_chosen.pkl.gz',
        'asas_timeseries_dirpath':user_path + '/scratch/asas_data/timeseries', #proj=131: user_path  +'/scratch/asas_fullcat_lcs', #tranx ACVS: '/home/pteluser/scratch/asas_data/timeseries',
        'asas_url_prefix':'http://www.astrouw.edu.pl/cgi-asas/asas_cgi_get_data?',
        'asas_url_suffix':',asas3',
        'project_id':126, #ACVS=126, ASAS_15Msrcs = 131 prior to 20120207
    }
    asas_pars.update(pars)



    if 0:
        ### just generate timeseries for a single ASAS source:
        asas_dt = ASAS_Data_Tools(pars=asas_pars)
        asas_dt.get_asas_timeseries_for_url(url="http://www.astrouw.edu.pl/cgi-asas/asas_cgi_get_data?220131+0550.1,asas3")


    if 0:
        # Branamir Sasar Stripe82 rrlyrae program is proj_id=128
        ts_pars = { \
            'project_id':128,
            'source_data_fpath':'/home/pteluser/analysis/tutor_data_cache/project_128/table2.dat',
            'ts_data_dirpath':'/home/pteluser/analysis/tutor_data_cache/project_128/table1',
            'ts_filename_colname':'id',
            'ts_source_colname':'id',
            'ts_filename_suffix':'.dat',
            'observation_time_format':'mjd',
            'mag_null_value':-99,     # magnitude value in datafiles which represents nodata / reading
            'delimiter':' ',
            'dtype':{'names':('id', 'type', 'P', 'uA', 'u0', 'uE', 'uT', 'gA', 'g0', 'gE', 'gT', 'rA', 'r0', 'rE', 'rT', 'iA', 'i0', 'iE', 'iT', 'zA', 'z0', 'zE', 'zT'),
                   'formats':('i8', 'S2',   'f8','f8', 'f8', 'f8', 'i4', 'f8', 'f8', 'f8', 'i4', 'f8', 'f8', 'f8', 'i4', 'f8', 'f8', 'f8', 'i4', 'f8', 'f8', 'f8', 'i4')}
            }
        ts_pars.update(pars)
        Timeseries_Insert = TimeseriesInsert(pars=ts_pars)
        Timeseries_Insert.main()
        sys.exit()



    if 0:
        ### for changing asas ra from hours decimal form to degress decimal form
        asas_dt = ASAS_Data_Tools(pars=asas_pars)
        #asas_dt.convert_ra_hrs_to_deg()
        asas_dt.update_asas_source_ra_dec()


    
    # 2012-02-13 DEBUG:
    #asas_dt = ASAS_Data_Tools(pars=asas_pars)
    #import h5py
    #import numpy
    #fr = h5py.File('/Data/dstarr/Data/asas_ACVS_50k_data/aperture_plot_sanitycheck.hdf5', 'r')
    #aperture = numpy.array(fr['aperture'])
    #mag = numpy.array(fr['mag'])
    #fr.close()
    #asas_dt.plot_aperture_mag_relation(aperture_list=aperture, mag_list=mag, generate_aperture_hist_plot=True)

    if 1:
        ### For ASAS data ingest

        # get limits dict from tranx table

        asas_dt = ASAS_Data_Tools(pars=asas_pars)
        asas_dt.timeseries_main(write_source_file=False) # 20120216: dstarr adds True flag

        sys.exit()

    if 0:
        # ROTOR program is proj_id=124
        ts_pars = { \
            'project_id':124,
            'source_data_fpath':'/home/pteluser/analysis/tutor_data_cache/project_124/asu.tsv',
            'ts_data_dirpath':'/home/pteluser/analysis/tutor_data_cache/project_124/ts_data',
            'ts_filename_colname':'fname',
            'ts_source_colname':'source_name',
            'ts_filename_suffix':'',
            'delimiter':'\t',
            'dtype':{'names':('ra', 'dec', 'id', 'source_name', 'ra_s', 'dec_s', 'm_b', 'm_v', 'spec_type', 'fname'),
                 'formats':('f8','f8', 'i8', 'S10',         'S10',   'S9',   'S5',  'S5',  'S11',       'S13')}
            }
        ts_pars.update(pars)
        Timeseries_Insert = TimeseriesInsert(pars=ts_pars)
        Timeseries_Insert.main()
        sys.exit()
    if 0:
        #####  For updating / copying debosscher dataset in TUTOR:
        debosscher_pars = { \
            'old_proj_id':122,
            'new_proj_id':123, # NOTE: user must make sure this is the max(project_id)
            'joey_xml_dirpath':'/home/pteluser/analysis/debos_newHIPP_data/xmls',
            'old_proj122_ogle_dat_dirpath':'/home/pteluser/analysis/debos_old_lyra_tutor_import/project_122/',
            'hipdict_with_ts_pklgz_fpath':'/home/pteluser/analysis/debos_newHIPP_data/hipdict_with_ts.pkl.gz',
            }
        debosscher_pars.update(pars)
        Tutor_Deboss_Proj_Insert = TutorDebosscherProjectInsert(pars=debosscher_pars)
        Tutor_Deboss_Proj_Insert.debosscher_main(debug=True)
        #####


    #Tutor_Deboss_Proj_Insert = TutorProjectInsert(pars=debosscher_pars)

    """

### For analysis of the limiting-magnitude table for assas_fullcatalog analysis:

### Get p% percentile:
SET @perc = 0.35;
SELECT @n_gt0 := COUNT(*) FROM asas_fullcat_frame_limits where n > 0 ;
SELECT @n_perc := FLOOR(COUNT(*) * @perc) FROM asas_fullcat_frame_limits where n > 0 ;
SET @s = CONCAT("SELECT ", @perc, " AS perc, n, ", @n_gt0, " AS N_gt_0 FROM asas_fullcat_frame_limits WHERE n > 0 ORDER BY  n LIMIT  1 OFFSET ", @n_perc);
PREPARE stmt FROM @s;
EXECUTE stmt;

    """
