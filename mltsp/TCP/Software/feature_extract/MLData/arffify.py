#!/usr/bin/env python

"""
arffify

  makes ARFF files out of queries to the TCP/TUTOR DB.

USAGE:
 [0] mkdir XML
 [1] In a separate window, make a tunnel to the test XML-RPC server on the linux boxes
     print "ssh  -L 34583:192.168.1.65:34583 lyra.berkeley.edu"
 [2] Start python

py> import arffify
py> a = arffify.Maker(search=["Cepheids","RR Lyrae - Asymmetric","Mira","W Ursae Majoris",])  ## search is a list of string names to look up

"""
from __future__ import print_function
from __future__ import unicode_literals
import os,sys
#try:
#   import amara
#except:
#   pass
try:
    import xmlrpclib
except ImportError:
    import xmlrpc.client as xmlrpclib
import urllib
import copy
import datetime
try:
    import MySQLdb
except:
    pass
import time
import glob

from ...feature_extract.Code.extractors import mlens3

# pre 20091117:
#skip_features = ['beyond1std', 'chi2', 'chi2_per_deg', 'dc', 'example', 'first_freq', 'freq1_harmonics_freq_1', 'freq1_harmonics_freq_2', 'freq1_harmonics_freq_3', 'freq2_harmonics_amplitude_error_1', 'freq2_harmonics_amplitude_error_2', 'freq2_harmonics_amplitude_error_3', 'freq2_harmonics_freq_1', 'freq2_harmonics_freq_2', 'freq2_harmonics_freq_3', 'freq3_harmonics_amplitude_error_1', 'freq3_harmonics_amplitude_error_2', 'freq3_harmonics_amplitude_error_3', 'freq3_harmonics_freq_1', 'freq3_harmonics_freq_2', 'freq3_harmonics_freq_3', 'freq_searched_max', 'max', 'median', 'min', 'old_dc', 'ratio21', 'ratio31', 'ratio32', 'ratioRUfirst', 'second', 'std', 'third', 'wei_av_uncertainty', 'weighted_average', 'distance_in_arcmin_to_nearest_galaxy', 'distance_in_kpc_to_nearest_galaxy', 'freq1_harmonics_nharm', 'freq2_harmonics_nharm', 'freq2_harmonics_signif', 'freq3_harmonics_nharm', 'freq3_harmonics_signif', 'percent_amplitude', 'max_slope'] #, 'n_points'

skip_features =['chi2',
        'chi2_per_deg',
        'dc',
        'distance_in_arcmin_to_nearest_galaxy',
        'distance_in_kpc_to_nearest_galaxy',
        'example',
        'first_freq',
        'freq1_harmonics_freq_1',
        'freq1_harmonics_freq_2',
        'freq1_harmonics_freq_3',
        'freq1_harmonics_nharm',
        'freq2_harmonics_amplitude_error_1',
        'freq2_harmonics_amplitude_error_2',
        'freq2_harmonics_amplitude_error_3',
        'freq2_harmonics_freq_1',
        'freq2_harmonics_freq_2',
        'freq2_harmonics_freq_3',
        'freq2_harmonics_nharm',
        'freq2_harmonics_signif',
        'freq3_harmonics_amplitude_error_1',
        'freq3_harmonics_amplitude_error_2',
        'freq3_harmonics_amplitude_error_3',
        'freq3_harmonics_freq_1',
        'freq3_harmonics_freq_2',
        'freq3_harmonics_freq_3',
        'freq3_harmonics_nharm',
        'freq3_harmonics_signif',
        'freq_searched_max',
        'max',
        #'max_slope', # 2010525 dstarr re-enables this since it looks like the algorithm might have worth when looking at old .arffs and also I dont recall why I disabled it
        'median',
        'min',
        'old_dc',
        #'percent_amplitude', # 2010517 dstarr re-enables this to see if useful, althoguh return output of extractor looks kludgey and nonlinear.
        'ratio21',
        'ratio31',
        'ratio32',
        'ratioRUfirst',
        'second',
        #'std', # 2010525 dstarr re-enables this since skew has been useful (although it may not be useful)
        'third',
        'wei_av_uncertainty',
        'weighted_average',
        'closest_in_light',
        'closest_light_absolute_bmag',
        'closest_light_angle_from_major_axis',
        'closest_light_angular_offset_in_arcmin',
        'closest_light_dm',
        'closest_light_physical_offset_in_kpc',
        'closest_light_ttype',
        'freq1_harmonics_amplitude_error_0',
        'freq1_harmonics_moments_err_0',
        'freq1_harmonics_peak2peak_flux_error',
        'freq1_harmonics_rel_phase_error_0',
        'freq2_harmonics_amplitude_error_0',
        'freq2_harmonics_moments_err_0',
        'freq2_harmonics_rel_phase_error_0',
        'freq3_harmonics_amplitude_error_0',
        'freq3_harmonics_moments_err_0',
        'freq3_harmonics_rel_phase_error_0',
        #20120126 commentout'n_points', # This is required for internal use by plugin_classifier.py  Thankfully it doesn't seem to be used much in classifier decision trees, though.
        'sdss_best_dm',
        'sdss_best_offset_in_kpc',
        'sdss_best_offset_in_petro_g',
        'sdss_best_z',
        'sdss_best_zerr',
        'sdss_dered_g',
        'sdss_dered_i',
        'sdss_dered_r',
        'sdss_dered_u',
        'sdss_dered_z',
        'sdss_dist_arcmin',
        'sdss_in_footprint',
        'sdss_nearest_obj_type',
        'sdss_petro_radius_g',
        'sdss_photo_rest_abs_g',
        'sdss_photo_rest_abs_i',
        'sdss_photo_rest_abs_r',
        'sdss_photo_rest_abs_u',
        'sdss_photo_rest_abs_z',
        'sdss_photo_rest_gr',
        'sdss_photo_rest_iz',
        'sdss_photo_rest_ri',
        'sdss_photo_rest_ug',
        'sdss_chicago_class', # 2010525 dstarr adds
        'sdss_first_flux_in_mjy', # 2010525 dstarr adds
        'sdss_first_offset_in_arcsec', # 2010525 dstarr adds
        'sdss_spec_confidence', # 2010525 dstarr adds
        'sdss_rosat_offset_in_arcsec',
        'sdss_rosat_offset_in_sigma']

positional_features = ["ecpb", "galb", "gall", "ecpl"] #"distance_in_arcmin_to_nearest_galaxy", "distance_in_kpc_to_nearest_galaxy"


def get_class_abrv_lookup_from_header(train_arff_fpath):
    """ Given a .arff which is to be used for training, return the
    {class_abrev:class_fullname} dictionary parsed from the header, if
    it exists.
    """
    lines = open(train_arff_fpath).readlines()
    class_lookup_dict = {}
    for line in lines:
        if line[:20] == "%% class_lookup_dict":
            exec(line[3:])
            break # get out of loop
    return class_lookup_dict

class Maker:

    #print "ssh lyra.berkeley.edu -c blowfish -X -L 13306:127.0.0.1:3306"
    #   'skip_sci_class_list':['vs', 'GCVS', 'NEW', ''], # Science classes to skip from adding to .arff
    #   'disambiguate_sci_class_dict':{'CEP':'c', # Ambiguous key classes are given value class_name
    #                      'dc':'c',
    #                      'RR':'rr-lyr',
    #                      'Nonstellar':'ML',
    #                      'Pulsating':'puls',
    #                      },
    pars = {'tcptutor_hostname':'lyra.berkeley.edu',
        'tcptutor_username':'pteluser',
        'tcptutor_password':'Edwin_Hubble71',
        'tcptutor_port':     3306, # 13306,
        'tcptutor_database':'tutor',
            'classdb_hostname':'127.0.0.1', #'192.168.1.25',
            'classdb_username':'dstarr', #'pteluser',
            'classdb_port':     3306,
            'classdb_database':'source_test_db', #'source_db',
        't_sleep':0.2,
        'number_threads':4,
        'tcp_tutor_srcid_offset':100000000,
        'local_xmls_fpath':os.path.expandvars('$HOME/scratch/TUTOR_vosources'),
        'skip_sci_class_list':['','Variable Stars'], #20110202: dstarr excludes  'UNKNOWN', since unclassified ASAS sources need o be included in the arff files.  # Science classes to skip from adding to .arff
        'disambiguate_sci_class_dict':{'Pulsating Variable Stars':'Pulsating Variable',#'Pulsating Variable':'Pulsating Variable Stars', #20100702 disable: 'Pulsating Variable Stars':'Pulsating Variable', # Ambiguous key classes are given value class_name
                           'Cepheid Variable':'Classical Cepheid',
                           'Cepheids':'Classical Cepheid',
                           'Classical Cepheids':'Classical Cepheid', #20091115: dstarr adds
                           'Classical Cepheids, Symmetrical':'Classical Cepheid', # 20091119: kludgy subclass assumption
                           'Symmetrical':'Classical Cepheid', # 20091119: kludgy subclass assumption
                           'Classical Cepheid Multiple Modes Symmetrical':'Multiple Mode Cepheid', #20091115: dstarr adds
                           'RR-Lyrae stars, subtype ab':'RR Lyrae, Fundamental Mode', #20091117: would like: 'RR-Lyrae stars, subtype ab':'RR Lyrae, Fundamental Mode',
                           'RR Lyrae - Near Symmetric':'RR Lyrae - First Overtone',
                           'Contact Systems':'Binary',
                           'Delta-Scuti stars':'Delta Scuti',
                           'Algol (Beta Persei)':'Beta Persei',
                           'Algol, with third?':'Beta Persei',
                           'Algol, semidetached, pulsating component':'Beta Persei',
                           'Beta Cephei, massive, rapidly rotating, multiperiodicity':'Beta-Cephei stars',
                           }, #20091117: disabling this since seems incorrect since seperate sub-types:  'RR Lyrae, First Overtone':'RR Lyrae, Fundamental Mode',
        'hardcoded_class_abrv_lookup': \
            {'ACV': 'Alpha2 Canum Venaticorum',
             'ACVO': 'Alpha2 CVn - Rapily Oscillating',
             'ACYG': 'Alpha Cygni',
             'AGN': 'Active Galactic Nuclei',
             'AM': 'AM Her',
             'AR': 'Detached - AR Lacertae',
             'BCEP': 'Beta Cephei',
             'BCEPS': 'Beta Cephei - Short Period',
             'BE': 'Be star',
             'BL-Lac': 'BL Lac',
             'BLBOO': 'Anomalous Cepheids',
             'BLZ': 'Blazar',
             'BY': 'BY Draconis',
             'CEP': 'Cepheids',
             'CEP(B)': 'Cepheids - Multiple Modes',
             'CW': 'W Virginis',
             'CWA': 'W Virginis - Long Period',
             'CWB': 'W Virigins - Short Period',
             'Cataclysmic': 'Cataclysmic (Explosive and Novalike) Variable Stars',
             'D': 'Detached',
             'DCEP': 'Delta Cep',
             'DCEPS': 'Delta Cep - Symmetrical',
             'DM': 'Detached - Main Sequence',
             'DQ': 'DQ Herculis Variable (Intermediate Polars)',
             'DS': 'Detached - With Subgiant',
             'DSCT': 'Delta Scuti',
             'DSCTC': 'Delta Scuti - Low Amplitude',
             'DW': 'W Ursa Majoris',
             'DrkMatterA': 'Dark Matter Anniliation Event',
             'E': 'Eclipsing Binary Systems',
             'EA': 'Algol (Beta Persei)',
             'EB': 'Beta Lyrae',
             'ELL': 'Rotating Ellipsoidal',
             'EP': 'Eclipsed by Planets',
             'EW': 'W Ursae Majoris -  W UMa',
             'EWa': 'W Ursae Majoris- a',
             'EWs': 'W Ursae Majoris- s',
             'Eclipsing': 'Close Binary Eclipsing Systems',
             'Eruptive': 'Eruptive Variable Stars',
             'FKCOM': 'FK Comae Berenices',
             'FU': 'FU Orionis',
             'GCAS': 'Gamma Cas',
             'GCVS': 'Variable Stars',
             'GDOR': 'Gamma Doradus',
             'GRB': 'Gamma-ray Bursts',
             'GS': 'Systems with Supergiant(s)',
             'GalNuclei': 'Galaxy Nuclei ',
             'I': 'Irregular',
             'IA': 'Irregular Early O-A',
             'IB': 'Irregular Intermediate F-M',
             'IN': 'Orion',
             'IN(YY)': 'Orion with Absorption',
             'INA': 'Orion Early Types (B-A or Ae)',
             'INB': 'Orion Intermediate Types (F-M or Fe-Me)',
             'INT': 'Orion T Tauri',
             'IS': 'Rapid Irregular',
             'ISA': 'Rapid Irregular Early Types (B-A or Ae)',
             'ISB': 'Rapid Irregular Intermediate to Late (F-M and Fe-Me)',
             'K': 'Contact Systems',
             'KE': 'Contact Systems - Early (O-A)',
             'KW': 'Contact Systems - W Ursa Majoris',
             'L': 'Slow Irregular',
             'LB': 'Slow Irregular - Late Spectral Type (K, M, C, S)',
             'LC': 'Irregular Supergiants',
             'LPB': 'Long Period B',
             'LSB': 'Long Gamma-ray Burst',
             'M': 'Mira',
             'ML': 'Microlensing Event',
             'N': 'Novae',
             'NA': 'Fast Novae',
             'NB': 'Slow Novae',
             'NC': 'Very Slow Novae',
             'NEW': 'New Variability Types',
             'NL': 'Novalike Variables',
             'NR': 'Recurrent Novae',
             'Nonstellar': 'Variable Sources (Non-stellar)',
             'OVV': 'Optically Violent Variable Quasar (OVV)',
             'PN': 'Systems with Planetary Nebulae',
             'PSR': 'Optically Variable Pulsars',
             'PVTEL': 'PV Telescopii',
             'Polars': 'Polars',
             'Pulsating': 'Pulsating Variable Stars',
             'R': 'Close Binary with Reflection',
             'RCB': 'R Coronae Borealis',
             'RPHS': 'Very Rapidly Pulsating Hot (subdwarf B)',
             'RR': 'RR Lyrae',
             'RR(B)': 'RR Lyrae - Dual Mode',
             'RRAB': 'RR Lyrae - Asymmetric',
             'RRC': 'RR Lyrae - Near Symmetric',
             'RRcl': 'RR Lyrae -- Closely Spaced Modes',
             'RRe': 'RR Lyrae -- Second Overtone Pulsations',
             'RS': 'RS Canum Venaticorum',
             'RV': 'RV Tauri',
             'RVA': 'RV Tauri - Constant Mean Magnitude',
             'RVB': 'RV Tauri - Variable Mean Magnitude',
             'Rotating': 'Rotating Variable Stars',
             'SD': 'Semidetached',
             'SDOR': 'S Doradus',
             'SGR': 'Soft Gamma-ray Repeater',
             'SHB': 'Short Gamma-ray Burst',
             'SN': 'Supernovae',
             'SNI': 'Type I Supernovae',
             'SNII': 'Type II Supernovae',
             'SNIIL': 'Type II-L',
             'SNIIN': 'Type IIN',
             'SNIIP': 'Type IIP',
             'SNIa': 'Type Ia',
             'SNIa-pec': 'Peculiar Type Ia Supernovae',
             'SNIa-sc': 'Super-chandra Ia supernova',
             'SNIb': 'Type Ib',
             'SNIc': 'Type Ic',
             'SNIc-pec': 'Peculiar Type Ic Supernovae',
             'SR': 'Semiregular',
             'SRA': 'Semiregular - Persistent Periodicity',
             'SRB': 'Semiregular - Poorly Defined Periodicity',
             'SRC': 'Semiregular Supergiants',
             'SRD': 'Semiregular F, G, or K',
             'SRS': 'Semiregular Pulsating Red Giants',
             'SSO': 'Solar System Object',
             'SXARI': 'SX Arietis',
             'SXPHE': 'SX Phoenicis  - Pulsating Subdwarfs',
             'TDE': 'Tidal Disruption Event',
             'UG': 'U Geminorum',
             'UGSS': 'SS Cygni',
             'UGSU': 'SU Ursae Majoris',
             'UGZ': 'Z Camelopardalis',
             'UV': 'UV Ceti',
             'UVN': 'Flaring Orion Variables',
             'UXUma': 'UX Uma',
             'WD': 'Systems with White Dwarfs',
             'WR': 'Eruptive Wolf-Rayet',
             'WR(1)': 'Systems with Wolf-Rayet Stars',
             'X': 'X-Ray Sources, Optically Variable',
             'XB': 'X-Ray Bursters',
             'XF': 'Fluctuating X-Ray Systems',
             'XI': 'X-ray Irregulars',
             'XJ': 'X-Ray Binaries with Jets',
             'XND': 'X-Ray, Novalike',
             'XNG': 'X-Ray, Novalike with Early Type supergiant or giant',
             'XP': 'X-Ray Pulsar',
             'XPR': 'X-Ray Pulsar, with Reflection',
             'XPRM': 'X-Ray Pulsar with late-type dwarf',
             'XRM': 'X-Ray with late-type dwarf, un-observed pulsar',
             'ZAND': 'Symbiotic Variables',
             'ZZ': 'ZZ Ceti',
             'ZZA': 'ZZ Ceti - Only H Absorption',
             'ZZB': 'ZZ Ceti - Only He Absorption',
             'ZZO': 'ZZ Ceti showing HeII',
             'ac': 'Alpha Cygni',
             'aii': 'Alpha2 Canum Venaticorum',
             'alg': 'Algol (Beta Persei)',
             'am': 'AM Herculis (True Polar)',
             'amcvn': 'AM Canum Venaticorum',
             'b': 'Binary',
             'bc': 'Beta Cephei',
             'be': 'Be Star',
             'bl': 'Short period (BL Herculis)',
             'bly': 'Beta Lyrae',
             'by': 'BY Draconis',
             'c': 'Cepheid Variable',
             'ca': 'Anomolous Cepheid',
             'cc': 'Core Collapse Supernovae',
             'cm': 'Multiple Mode Cepheid',
             'cn': 'Classical Novae',
             'cv': 'Cataclysmic Variable',
             'dc': 'Classical Cepheid',
             'dqh': 'DQ Herculis (Intermdiate Polars)',
             'ds': 'Delta Scuti',
             'dsm': 'Delta Scuti - Multiple Modes',
             'ell': 'Ellipsoidal',
             'er': 'ER Ursae Majoris',
             'ev': 'Eruptive Variable',
             'fk': 'FK Comae Berenices',
             'fsrq': 'Flat Spectrum Radio Quasar',
             'fuor': 'FU Orionis',
             'gc': 'Gamma Cassiopeiae',
             'gd': 'Gamma Doradus',
             'grb': 'Gamma Ray Burst',
             'gw': 'GW Virginis',
             'hae': 'Herbig AE',
             'haebe': 'Herbig AE/BE Star',
             'i': 'Type I Supernovae',
             'ib': 'Type Ib Supernovae',
             'ic': 'Type Ic Supernovae',
             'ii': 'Type II Supernovae',
             'iii': 'Three or More Stars',
             'iin': 'Type II N',
             'lamb': 'Lambda Eridani',
             'lboo': 'Lambda Bootis Variable',
             'lgrb': 'Long GRB',
             'mira': 'Mira',
             'msv': 'Multiple Star Variables',
             'n-l': 'Novalike',
             'nov': 'Novae',
             'ov': 'Orion Variable',
             'p': 'Polars',
             'pi': 'Pair Instability Supernovae',
             'piic': 'Population II Cepheid',
             'plsr': 'Pulsar',
             'psys': 'Systems with Planets',
             'puls': 'Pulsating Variable',
             'pvt': 'PV Telescopii',
             'pwd': 'Pulsating White Dwarf',
             'qso': 'QSO',
             'rcb': 'R Coronae Borealis',
             'rn': 'Recurrent Novae',
             'rot': 'Rotating Variable',
             'rr-ab': 'RR Lyrae, Fundamental Mode',
             'rr-c': 'RR Lyrae, First Overtone',
             'rr-cl': 'RR Lyrae, Closely Spaced Modes',
             'rr-d': 'RR Lyrae, Double Mode',
             'rr-e': 'RR Lyrae, Second Overtone',
             'rr-lyr': 'RR Lyrae',
             'rscvn': 'RS Canum Venaticorum',
             'rv': 'RV Tauri',
             'rvc': 'RV Tauri, Constant Mean Brightness',
             'rvv': 'RV Tauri, Variable Mean Brightness',
             'sdc': 'Symmetrical',
             'sdorad': 'S Doradus',
             'seyf': 'Seyfert',
             'sgrb': 'Short GRB',
             'shs': 'Shell Star',
             'sn': 'Supernovae',
             'sr-a': 'SRa (Z Aquarii)',
             'sr-b': 'SRb',
             'sr-c': 'SRc',
             'sr-d': 'SRd',
             'sreg': 'Semiregular Pulsating Variable',
             'srgrb': 'Soft Gamma Ray Repeater',
             'ssc': 'SS Cygni',
             'su': 'SU Ursae Majoris',
             'sv': 'Symbiotic Variable',
             'sw': 'SW Sextantis',
             'sx': 'SX Phoenicis',
             'sxari': 'SX Arietis',
             'tia': 'Type Ia Supernovae',
             'tt': 'T Tauri',
             'ttc': 'Classical T Tauri',
             'ttw': 'Weak-lined T Tauri',
             'ug': 'U Geminorum',
             'uv': 'UV Ceti Variable',
             'ux': 'UX Ursae Majoris',
             'vs': 'Variable Stars [Alt]',
             'vy': 'VY Scl',
             'wr': 'Wolf-Rayet',
             'wu': 'W Ursae Majoris',
             'wv': 'Long Period (W Virginis)',
             'wz': 'WZ Sagittae',
             'xrb': 'X Ray Burster',
             'xrbin': 'X Ray Binary',
             'zc': 'Z Camelopardalis',
             'zz': 'ZZ Ceti',
             'zzh': 'ZZ Ceti, H Absorption Only',
             'zzhe': 'ZZ Ceti, He Absorption Only',
                 'zzheii': 'ZZ Ceti, With He-II'} # this is hopefully updated occasionally by a user (although seemingly pretty complete at this point).
           }


    def __init__(self,verbose=True, therange=None, dorun=True,\
             skip_class=False, local_xmls=False,\
             outfile = "maker.arff", \
             convert_class_abrvs_to_names=False, \
             search=["Cepheids","RR Lyrae - Asymmetric","RR Lyrae - Dual Mode","RR Lyrae - Near Symmetric","Cepheids - Multiple Modes"], ignore_positional_features=True, flag_retrieve_class_abrvs_from_TUTOR=False, local_xmls_fpath='', class_abrv_lookup={}, add_srcid_to_arff=False):
        self.pars['local_xmls_fpath'] = local_xmls_fpath
        self.add_srcid_to_arff = add_srcid_to_arff
        self.skip_class = skip_class
        self.local_xmls = local_xmls
        self.convert_class_abrvs_to_names =convert_class_abrvs_to_names
        self.flag_retrieve_class_abrvs_from_TUTOR = flag_retrieve_class_abrvs_from_TUTOR
        self.verbose = True
        self.outfile = outfile
        self.search = search
        self.skips = skip_features

        if self.flag_retrieve_class_abrvs_from_TUTOR:
            self.retrieve_class_abrvs_from_TUTOR()
        elif len(class_abrv_lookup) > 0:
            self.class_abrv_lookup = class_abrv_lookup
        else:
            self.class_abrv_lookup = \
                      self.pars['hardcoded_class_abrv_lookup']
        #elif self.convert_class_abrvs_to_names:
        #   # Obsolete to retrieve from TCP class database:
        #   self.populate_classname_lookup_dict()

        if ignore_positional_features:
            self.skips.extend(positional_features)
        if dorun:
            self.run()


    def retrieve_class_abrvs_from_TUTOR(self):
        """ Retrieve <science class acronym>:<science class name>
        relations from TUTOR database.
        Fill self.class_abrv_lookup{} with the relation.
        """
        self.db = MySQLdb.connect(host=self.pars['tcptutor_hostname'], \
                                     user=self.pars['tcptutor_username'], \
                                     passwd=self.pars['tcptutor_password'],\
                                     db=self.pars['tcptutor_database'],\
                                     port=self.pars['tcptutor_port'])
        self.cursor = self.db.cursor()
        select_str = "SELECT class_short_name, class_name FROM classes" # class_id
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        self.class_abrv_lookup = {}
        for result in results:
            #if self.class_abrv_lookup.has_key(result[0]):
            #   print "!!! ALREADY HAVE:", result[0],result[1],  self.class_abrv_lookup[result[0]]
            self.class_abrv_lookup[result[0]] = result[1]


    # 20081023 Obsolete:
    def populate_classname_lookup_dict(self):
        """ Populate a dictionary which translates science class
        abreviation names to full science class names.
        """
        classdb_db = MySQLdb.connect(\
            host=self.pars['classdb_hostname'], \
            user=self.pars['classdb_username'], \
            db=self.pars['classdb_database'],\
            port=self.pars['classdb_port'])
        classdb_cursor = classdb_db.cursor()
        select_str = "SELECT class_short_name,class_name from classid_lookup"
        classdb_cursor.execute(select_str)
        results = classdb_cursor.fetchall()
        # KLUDGE: There are some ?mislabeled? class abreviations, which I will clarify here:
        self.class_abrv_lookup = {'ii': 'Type II Supernovae',
                      'ab': 'RR Lyrae - Asymmetric',
                      'bs': 'SX Phoenicis  - Pulsating Subdwarfs',
                      'sx': 'SX Phoenicis  - Pulsating Subdwarfs',
                      'c': 'RR Lyrae - Near Symmetric',
                      'gd': 'Gamma Doradus',
                      'mira': 'Mira',
                      'ml': 'MIcrolensing Event',
                      'ptcep': 'Population II Cepheid',
                      'rg': 'Semiregular Pulsating Red Giants',
                      'wu': 'W Ursa Majoris',
                      'rrd':'Double Mode RR Lyrae'
                      }
        for result in results:
            self.class_abrv_lookup[result[0].lower()] = result[1]


    def get_srcid_list_by_name(self,search):

        tmplist = []
        if type(search) == type("s"):
            search = [search]
        for s in search:
            if s is None or s == "":
                continue
            params = urllib.urlencode({'fmt': "json", 't': "Source", 'f1': "Class_Name", "o1": "IS","v1": s})
            f = urllib.urlopen("http://lyra.berkeley.edu/tutor/pub/find_ids.php?%s" % params)
            b =  """a = %s""" % f.read()
            exec(b)
            if self.verbose:
                print("[%s] %i objects returned" % (s,len(a)))
            tmplist.extend([int(x) + self.pars['tcp_tutor_srcid_offset'] for x in a])
        tmplist = list(set(tmplist))
        return tmplist


    # obsolete? :
    def get_srcid_list_from_DB(self):
        self.db = MySQLdb.connect(host=self.pars['tcptutor_hostname'], \
                                     user=self.pars['tcptutor_username'], \
                                     passwd=self.pars['tcptutor_password'],\
                                     db=self.pars['tcptutor_database'],\
                                     port=self.pars['tcptutor_port'])
        self.cursor = self.db.cursor()
        select_str = """SELECT DISTINCT sources.source_id FROM
    sources WHERE   EXISTS(SELECT Observations.Observation_ID FROM
    Observations WHERE Observations.Source_ID = sources.Source_ID)"""
        self.cursor.execute(select_str)
        results = self.cursor.fetchall()
        srcid_list = []
        for result in results:
            srcid_list.append(result[0] + self.pars['tcp_tutor_srcid_offset'])
        del self.cursor
        return srcid_list


    def run(self):
        self.therange = self.get_srcid_list_by_name(self.search)
        if self.local_xmls:
            self.populate_features_and_classes_using_local_xmls()
        else:
            self.populate_features_and_classes()
        self.write_arff()
        #tmprange = ["100009020-100009360"]
        #self.therange = self.get_srcid_list()
        #self.getnums(tmprange)
        #self.populate_features_and_classes()
        #self.write_arff()


    def write_arff(self, outfile='', classes_arff_str='', remove_sparse_classes=False, \
               n_sources_needed_for_class_inclusion=10, include_header=True, use_str_srcid=False):

        # TODO: form lookup dict string here:
        class_lookup_dict_str = "%% class_lookup_dict={"
        for abrv_class,long_class in self.class_abrv_lookup.items():
            class_lookup_dict_str += "'%s':'%s', " % (abrv_class,long_class)
        class_lookup_dict_str = class_lookup_dict_str[:-2] + '}\n'

        #if type(outfile) == type(sys.stdout):
        if type(outfile) == type(''):
            if len(outfile) > 0:
                self.outfile = outfile

            if os.path.exists(self.outfile):
                os.system("rm " + self.outfile)
            f = open(self.outfile,'w')
        else:
            # This is a file pointer, rather than a filepath string
            f = outfile
        if include_header:
            f.write('%% date = %s\n' % str(datetime.datetime.now()))
            f.write('%% \n')
            f.write(class_lookup_dict_str)
            f.write('%% \n')
            f.write('@RELATION ts\n\n')

        self.master_features =  list(self.master_features)
        self.master_classes = list(self.master_classes)
        # dstarr 20080526: Adding .sort() gives more consistant feature, class ordering in .arff files: self.class_abrv_lookup{}
        self.master_features.sort()
        self.master_classes.sort()

        if self.add_srcid_to_arff and include_header:
            f.write("@ATTRIBUTE source_id NUMERIC\n")

        condensed_master_features = [] # KLUDGE: This wont contain the duplicate feature instances of 'string' and 'float' which arises from NULL as well as REAL feature values which are often contained in different vosource.xmls
        # write in the feature and class defs
        for fea in self.master_features:
            if fea[1] == 'float':
                thetype = 'NUMERIC'
                condensed_master_features.append((fea[0],fea[1]))
            elif (fea[0],'float') not in self.master_features:
                if fea[0] == 'sdss_nearest_obj_type':
                    thetype = "{'galaxy','star','star_late', 'unknown', 'qso', 'hiz_qso', 'sky'}"
                    condensed_master_features.append((fea[0],'string'))
                else:
                            ### NOTE: this (not-currently 20110621) commented-out case will insert strings for cases which most likely are just NONE/NULL values only (except sdss_nearest_obj_type).  Weka barfs on STRING attributes, so we must exclude these from being included in .arff:
                                    thetype = 'STRING'
                                    condensed_master_features.append((fea[0],fea[1]))
                                    #continue # skip this attribute/feature
            else:
                # NOTICE I dont append to condensed_master_features[]
                continue # this is a case where 'NUMERIC' has already been written for this feature, and the stgin case probably arised from  a 'None' for this feature in oune of the ningested vosource.xmls.  So we skip.
            #print fea
            if include_header:
                f.write('@ATTRIBUTE %s %s\n' % (fea[0],thetype))


        ########## This removes sparsely sampled classes from being written to arff
        # KLUDGY, but it's 3am...
        #master_classes_backup = copy.copy(self.master_classes)
        if remove_sparse_classes:
            master_classes_new = []
            for class_name in self.all_class_list:
                if self.all_class_list.count(class_name) >= int(n_sources_needed_for_class_inclusion):
                    master_classes_new.append(class_name)
            self.master_classes = list(set(master_classes_new)) # collapse to a single item for each class
        ##########
        if self.skip_class:
            if len(classes_arff_str) == 0:
                classes_arff_str = "@ATTRIBUTE class {'AM Her','Active Galactic Nuclei','Algol (Beta Persei)','BL Lac','Be star','Beta Cephei','Beta Lyrae','Cepheids','Close Binary with Reflection','Contact Systems','DQ Herculis Variable (Intermediate Polars)','Delta Scuti','Detached - With Subgiant','Double Mode RR Lyrae','Eclipsed by Planets','Eruptive Wolf-Rayet','Gamma Doradus','Gamma-ray Bursts','Irregular Early O-A','Irregular Supergiants','Microlensing Event','Mira','Novalike Variables','Orion T Tauri','Polars','R Coronae Borealis','RR Lyrae','RR Lyrae - Asymmetric','RR Lyrae - Near Symmetric','S Doradus','SS Cygni','SU Ursae Majoris','SX Phoenicis  - Pulsating Subdwarfs','Semidetached','Semiregular - Persistent Periodicity','Semiregular - Poorly Defined Periodicity','Semiregular F, G, or K','Semiregular Pulsating Red Giants','Semiregular Supergiants','Type II Supernovae','Type Ia','Variable Stars','W Ursa Majoris','W Ursae Majoris -  W UMa','Z Camelopardalis'}\n"
            f.write(classes_arff_str)
            # OBSOLETE: f.write("@ATTRIBUTE class {'GCVS:Eclipsing:E:EA','GCVS:Eclipsing:E:EB','GCVS:Eclipsing:E:EW','GCVS:Pulsating:CEP','GCVS:Pulsating:M','GCVS:Pulsating:RR:RRAB'}\n")
        else:
            f.write("@ATTRIBUTE class {%s}\n" % (",".join(["""'%s'""" % x for x in self.master_classes])))
        f.write("\n@data\n")

        for obj in self.master_list:
            # # # # # #
            #20081117: dstarr comments out: #if not obj['class'] in self.master_classes:
            if remove_sparse_classes:
                if not obj.get('class','') in self.master_classes:
                    continue # skip this object due to being in a sparse class

            tmp = []
            #for fea in self.master_features:
            for fea in condensed_master_features:
                val = "?"
                if fea in obj['features']:
                    if fea[1] == 'float':
                        if ((obj['features'][fea] == "False") or
                            (str(obj['features'][fea]) == "inf") or
                            (str(obj['features'][fea]) == "nan")):
                            val = "?"
                        elif obj['features'][fea] != None:
                            val = str(obj['features'][fea])
                    else:
                        if obj['features'][fea] is None:
                            val = "?"
                        else:
                            val = """'%s'""" % str(obj['features'][fea])
                tmp.append(val)

            ##### Unused hack:
            #for fea in self.master_features:
            #   val = "?"
            #   if obj['features'].has_key(fea):
            #       str_fea_val = str(obj['features'][fea])
            #       if ((str_fea_val == "False") or
            #           (str_fea_val == "inf") or
            #           (str_fea_val == "nan") or
            #           (str_fea_val == "None")):
            #           val = "?"
            #       elif fea[1] == 'float':
            #           val = str(obj['features'][fea])
            #       else:
            #           val = """'%s'""" % str(obj['features'][fea])
            #   tmp.append(val)
            #####

            #out_str = ",".join(tmp)
            if self.add_srcid_to_arff:
                if use_str_srcid:
                    out_str = str(obj['num']) + ',' + ",".join(tmp)
                elif obj['num'].count('_') > 0:
                    # 20100810: dstarr adds this condition:
                    id_list = obj['num'].split('_')
                    source_id = int(id_list[0])
                    if (source_id > 100000000) and (source_id < 1000000000000):
                        source_id -= 100000000 # TUTOR source_id case
                    #out_str = str(source_id) + '_' + id_list[1] + ',' + ",".join(tmp)
                    # 20100901: we now have error-sets info in the fname/idnum: 100149234_0.90_1.xml
                    out_str = str(source_id) + '_' + id_list[1] + '_' + id_list[2] + ',' + ",".join(tmp)
                else:
                    source_id = int(obj['num'])
                    if (source_id > 100000000) and (source_id < 1000000000000):
                        source_id -= 100000000 # TUTOR source_id case
                    out_str = str(source_id) + ',' + ",".join(tmp)
            else:
                out_str = ",".join(tmp)
            if self.skip_class:
                out_str += ",?\n"
            else:
                out_str += ",'%s'\n" % (str(obj['class']))
            f.write(out_str)
        #if type(outfile) != type(sys.stdout):
        if type(outfile) == type(''):
            f.close()
            print("Wrote:", self.outfile)

    def populate_features_and_classes(self):

        self.master_list = []
        self.master_classes = []
        self.master_features = []
        self.grabber = XMLgrabber(verbose=self.verbose)
        for num in self.therange:
            print(num)
            x = self.grabber.grab(num)

            if x is not None:
                tmpdict = {}
                if not self.skip_class:
                    theclass = self._get_class_names(x)
                    self.master_classes.append(theclass)
                    tmpdict['class'] = theclass
                feat     = self._get_features(x)
                tmpdict.update({'num': num, 'file': os.path.basename(self.grabber.fname), 'features': feat})
                self.master_features.extend(feat.keys())
                self.master_list.append(copy.copy(tmpdict))

        self.master_features = set(self.master_features)
        self.all_class_list = copy.copy(self.master_classes)
        self.master_classes = set(self.master_classes)


    def populate_features_and_classes_using_local_xmls(self, \
                                       srcid_xml_tuple_list=[], \
                           use_local_xml_fpaths=False):
        """ Amara parse XML files/strings.
        Extract features and (if available, classes) from XML_string.

        Method created by jbloom, modified by dstarr.
        """
        self.master_list = []
        self.master_classes = []
        self.master_features = []
        # 20080617 dstarr disables this since it seems to be obsolete jbloom functionality:
        #self.grabber = XMLgrabber(verbose=self.verbose)

        xml_fname = '' # dstarr: this variable seemes KLUDGY since it is filled with the arbitrary last value from a "for loop"

        if use_local_xml_fpaths:
            if len(srcid_xml_tuple_list) == 0:
                # Then we get xml-strings from disk
                xml_fname_list = os.listdir(\
                                      self.pars['local_xmls_fpath'])
                # KLUDGE: This can potentially load a lot of xml-strings into memory:
                for xml_fname in xml_fname_list:
                    if xml_fname[-4:] != '.xml':
                        continue # skip this fpath
                    xml_fpath = "%s/%s" % (\
                           self.pars['local_xmls_fpath'], xml_fname)
                    num = xml_fname[:xml_fname.rfind('.')]
                    #srcid_xml_tuple_listcosw.append((num, xml_fpath))
                    srcid_xml_tuple_list.append((num, xml_fpath))
                    #print "Loading:", xml_fname
                    #xml_string = open(xml_fpath).read()
                    #srcid_xml_tuple_list.append((num, xml_string))

        for num,xml_string in srcid_xml_tuple_list:
            d = mlens3.EventData(xml_string)
            try:
                raw_class = d.data['VOSOURCE'].get('Classifications',{}).\
                    get('Classification',{}).get('class',{}).name
            except:
                raw_class = d.data['VOSOURCE'].get('CLASSIFICATIONS',{}).\
                      get('CLASSIFICATION',{}).get('SOURCE',{}).\
                      get('CLASS_SCHEMA',{}).get('CLASS',{}).get('dbname',{})
            tmpdict = {}
            if (not self.skip_class) and (len(raw_class) > 0):
                if self.convert_class_abrvs_to_names:
                    if raw_class in self.pars['skip_sci_class_list']:
                        print("Skipping GENERIC class:", raw_class, "for source:", num)
                        continue # skip this class since probably too generic to be useful for classification.
                    if raw_class not in self.class_abrv_lookup:
                        print("Skipping UNKNOWN class:", raw_class, "for source:", num)
                        continue # This class isn't in the lookup_dict{}, which is probably due to this class being added recently.  We will skip this source.
                    if raw_class in self.pars['disambiguate_sci_class_dict'].keys():
                        raw_class = self.pars['disambiguate_sci_class_dict'][raw_class]
                    theclass = self.class_abrv_lookup[raw_class]
                else:
                    if raw_class in self.pars['skip_sci_class_list']:
                        print("Skipping GENERIC class:", raw_class, "for source:", num)
                        continue # skip this class since probably too generic to be useful for classification.
                    if raw_class in self.pars['disambiguate_sci_class_dict'].keys():
                        raw_class = self.pars['disambiguate_sci_class_dict'][raw_class]
                    theclass = raw_class
                self.master_classes.append(theclass)
                tmpdict['class'] = theclass
            feat = self._get_features(d)
            tmpdict.update({'num': num, 'file': xml_fname  , 'features': feat})
            self.master_features.extend(feat.keys())
            self.master_list.append(copy.copy(tmpdict))
        self.master_features = set(self.master_features)
        self.all_class_list = copy.copy(self.master_classes)
        self.master_classes = set(self.master_classes)


    def generate_arff_line_for_vosourcexml(self, num='', xml_fpath=''):
        """ Given a vosource.xml fpath, calculate the structures and possibly
        .arff line for that source.
        This is intended to be called by IPythron ipengine.
        """
        d = mlens3.EventData(xml_fpath)
        try:
            raw_class = d.data['VOSOURCE'].get('Classifications',{}).\
              get('Classification',{}).get('class',{}).name
        except:
            raw_class = d.data['VOSOURCE'].get('CLASSIFICATIONS',{}).\
              get('CLASSIFICATION',{}).get('SOURCE',{}).\
              get('CLASS_SCHEMA',{}).get('CLASS',{}).get('dbname',{})
        tmpdict = {}
        if (not self.skip_class) and (len(raw_class) > 0):
            if self.convert_class_abrvs_to_names:
                if raw_class in self.pars['skip_sci_class_list']:
                    print("Skipping GENERIC class:", raw_class, "for source:", num)
                    return # skip this class since probably too generic to be useful for classification.
                if raw_class not in self.class_abrv_lookup:
                    print("Skipping UNKNOWN class:", raw_class, "for source:", num)
                    return # This class isn't in the lookup_dict{}, which is probably due to this class being added recently.  We will skip this source.
                if raw_class in self.pars['disambiguate_sci_class_dict'].keys():
                    raw_class = self.pars['disambiguate_sci_class_dict'][raw_class]
                theclass = self.class_abrv_lookup[raw_class]
            else:
                if raw_class in self.pars['skip_sci_class_list']:
                    print("Skipping GENERIC class:", raw_class, "for source:", num)
                    return#skip this class since probably too generic to be useful for classification
                if raw_class in self.pars['disambiguate_sci_class_dict'].keys():
                    raw_class = self.pars['disambiguate_sci_class_dict'][raw_class]
                theclass = raw_class
            tmpdict['class'] = theclass
        feat = self._get_features(d)
        tmpdict.update({'num': num, 'file': xml_fpath  , 'features': feat})

        #import pprint
        #pprint.pprint(tmpdict)

        ### This will be ipython task-client 'pulled':
        return tmpdict



    def _get_class_names(self,doc):
        ## parses an XML to get the classes
        class_name = doc.d['VOSOURCE']['Classifications']['Classification']['class']['name']
        return class_name


    def _get_features(self,doc):
        ret = {}
        #doc.feat_dict[filt][feat]
        #features = doc.xml_xpath(u"//Feature")
        n_epoch_filt_list = []
        for filt_name,filt_dict in doc.data['ts'].items():
            n_epoch_filt_list.append((len(dict(filt_dict[0])['val']),filt_name))
        n_epoch_filt_list.sort(reverse=True)
        try:
            filt_most_sampled = n_epoch_filt_list[0][1]
        except:
            return {}

        feat_xmldicts = doc.feat_dict.get('multiband',{})
        feat_xmldicts.update(doc.feat_dict.get(filt_most_sampled,{}))

        for feat_name,feat_dict in feat_xmldicts.items():
            #tmp = f.xml_xpath(u"val")[0]
            tmp = feat_dict['val']['_text']
            #if tmp.is_reliable == 'True':
            thetype = feat_dict['val']['datatype']
            if feat_dict['val']['is_reliable'] == 'True':
                #thetype = str(tmp.datatype)
                #thetype = feat_dict['val']['datatype']
                v = str(tmp)
                if (v == "None") or \
                   (v == "False"):
                    val = None
                else:
                    if str(thetype) == 'float':
                        try:
                            val = float(str(tmp))
                        except:
                            val = str(tmp)
                    else:
                        val = str(tmp)
            else:
                val = None
            if str(feat_name) not in self.skips:
                #ret.update({(str(f.name),str(thetype)): val})
                # if this is string, dont add if float exists
                # if this is float, replace string if string exists
                # This is KLUDGY, since it shows that we should not index dict with type() in the index tuple, but instead should just use the feature only:
                if thetype == 'string':
                    if (str(feat_name),'float') not in ret:
                        ret.update({(str(feat_name),thetype): val})
                elif thetype == 'float':
                    if (str(feat_name),'string') in ret:
                        ret.pop((str(feat_name),'string'))
                    ret.update({(str(feat_name),thetype): val})
                else:
                    ret.update({(str(feat_name),thetype): val})
        return ret

    # obsolete: 20090130: This wouldnt set <None> values for 'False', etc...
    def _get_features__old(self,doc):
        ret = {}
        features = doc.xml_xpath(u"//feature")
        for f in features:
            tmp = f.xml_xpath(u"val")[0]
            if tmp.is_reliable == 'True':
                thetype = tmp.datatype
                v = str(tmp)
                if v == "None":
                    val = None
                else:
                    if str(tmp.datatype) == 'float':
                        try:
                            val = float(str(tmp))
                        except:
                            val = str(tmp)
                    else:
                        val = str(tmp)
            else:
                val = None
            if str(f.name) not in self.skips:
                ret.update({(str(f.name),str(thetype)): val})
        return ret


    def getnums(self,tmprange):
        self.therange = []
        for i in tmprange:
            if i.find("-") != -1:
                ## we got a range
                tmp = i.strip().split("-")
                try:
                    tmp = range(int(tmp[0]),int(tmp[1]) + 1)
                    self.therange.extend(tmp)
                except:
                    pass

                continue
            try:
                print(i)
                tmp = int(i)
                self.therange.append(tmp)
            except:
                pass

class XMLgrabber:


    server     = None
    xmldir     = "/Users/jbloom/Projects/TCP/Software/feature_extract/MLData/XML/"
    #print "You might need to issue 'ssh  -L 34583:192.168.1.65:34583 lyra.berkeley.edu' if you haven't already"
    #server_url = "http://lyra.berkeley.edu:34583"
    server_url = "http://localhost:34583"

    def __init__(self,verbose=True,regrab=False):
        self.verbose=verbose
        self._connect()
        self.regrab = regrab


    def grab(self,num=None):
        self.fname = self.xmldir + str(num) + ".xml"
        if num and self.server is not None:
            if self.regrab or not os.path.exists(self.fname):
                try:
                    tmp = self.server.get_vosource_url_for_srcid(num)
                except:
                    return None
                if tmp.find('database_query_error') != -1:
                    if self.verbose:
                        print("No object number %i" % num)
                    return None
                tmp1 = amara.parse(tmp)
                fileloc = str(unicode(tmp1.A.href))
                h = urllib.urlretrieve(fileloc,self.fname)

            if os.path.exists(self.fname):
                return amara.parse(self.fname)
            else:
                return None
        else:
            return None

    def _connect(self):
        if self.server is None:
            self.server = xmlrpclib.ServerProxy(self.server_url)
        return

    def _disconnect(self):
        if self.server is not None:
            del self.server

    def __del(self):
        self._disconnect()



if __name__ == '__main__':
    #NOTE: command line execution of arffify.py is intended only to be called by generate_arff.php on lyra.

    sci_class_list = sys.argv[0].split(',')
    search_list = []
    #out_fpath = "/Volumes/BR1/Graham/Bloom-store/Josh/public_html/dstarr/vosource_outs/"
    #out_fpath = os.environ.get("TCP_DIR") + \
    #             'Software/feature_extract/MLData/sdss_sources.arff'
    #out_fpath = os.environ.get("TCP_DIR") + \
    #            'Software/feature_extract/MLData/TUTOR_sources.arff'
    out_fpath = '/tmp/arffify_test.arff'

    ###for sci_class_underscored in sci_class_list:
    ###    sci_class = sci_class_underscored.replace("___", " ")
    ###    out_fpath += sci_class_underscored.replace("___", "_")
    ###    search_list.append(sci_class)
    # TODO: parse the argv into seperate class-names
    # TODO: form outfile using these:
    #      /Volumes/BR1/Graham/Bloom-store/Josh/public_html/dstarr/vosource_outs/..<>..arf

    ### This searches a list of string names to look up:
    #a = Maker(search=search_list, outfile=out_fpath, skip_class=True, \
    #          local_xmls=True, convert_class_abrvs_to_names=True)


    # NOTE: parameter local_xmls=True can be used if populate_feat_db_using_TCPTUTOR_sources.py has been executed recently
    #  ( this generates the XML files)
    a = Maker(search=search_list, outfile=out_fpath, skip_class=False, \
          local_xmls=True, convert_class_abrvs_to_names=False, \
          local_xmls_fpath=os.path.expandvars('$HOME/scratch/vosource_subset'), flag_retrieve_class_abrvs_from_TUTOR=True)
