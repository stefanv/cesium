from __future__ import print_function
from __future__ import absolute_import
import numpy, sys
from .. import db_importer
from .storage import storage
from numpy import log, exp, arange, median, ceil, pi

from .gen_or_imp import gen_or_imp
import types

class from_xml(gen_or_imp):
    name = 'xml'
    def __init__(self,signals_list=[]):
        self.storer = storage()
        self.signals_list = signals_list
    def generate(self, xml_handle="/home/maxime/feature_extract/Code/source_5.xml", make_xml_if_given_dict=True, register = True):
        self.signalgen = {}
        self.sig = db_importer.Source(xml_handle=xml_handle,doplot=False, make_xml_if_given_dict=make_xml_if_given_dict)
        self.sdict = self.sig.x_sdict
        self.set_outputs() # this adds/fills self.signalgen[<filters>,multiband]{'input':{filled},'features':{empty},'inter':{empty}}
        # see (1) at EOF for output from above function
        self.storer.store(self.signalgen,self.signals_list, register=register)


        # see (2) at EOF for output from above function

    def reckon_err_axis(self,d,obs_ind,ucd_error_values=['stat.error','error']):
        """ figure out the column number for the error associated with index obs_ind """
        if 'units' in d and 'ordered_column_names' in d and 'ucds' in d:
            ucd_obs = d['ucds'][obs_ind]
            for i in range(len(d['ucds'])):
                if i == obs_ind:
                    continue
                if type(d['ucds'][i]) == bytes and d['ucds'][i].find(ucd_obs) != -1:
                    for e in ucd_error_values:
                        if d['ucds'][i].find(e) != -1:
                            return i
        return None

    def set_outputs(self):
        self.make_dics()
        nominal_flux_or_mag_err               = 0.10
        nominal_time_dependent_positional_err = 0.001 # degrees

        for band in self.sig.ts:
            dic = self.sig.ts[band]
            self.signaldata[band] = {} #20071206 dstarr adds this
            input_dic = self.sub_dics(self.signaldata[band]) # creates sub-dictionaries in this particular band, chooses the right one to receive input data
            #input_dic = dict(time_data=numpy.array(dic['t']), flux_data=numpy.array(dic['m']), rms_data=numpy.array(dic['m_err']))
            if "t" in dic:
                time = numpy.array(dic['t'])
            else:
                time = numpy.array([])

            ## JSB...adding units to the dictionary. Note that there is also UCD availability
            ## TODO....allow for multiple flux measurements in the same instance
            if 'units' in dic and 'ordered_column_names' in dic and 'ucds' in dic:
                # PTF characteristics:
                if 'mag_subtr' in dic['ordered_column_names']:
                    # NOTE: for PTF VOSource, which db_importer generated, the first 3 items (t,m,merr) are handled below.
                    for i_colname in range(3,len(dic['ordered_column_names'])):
                        colname = dic['ordered_column_names'][i_colname]
                        input_dic.update({(colname + '_unit'): dic['units'][i_colname],
                                  (colname + '_ucd'): dic['ucds'][i_colname],
                                  colname: numpy.array(dic[dic['ordered_column_names'][i_colname]])})
                ## TIME AXIS: REQUIRED
                time_axis            = 0
                try:
                    input_dic.update({'time_data_unit': dic['units'][time_axis],
                              'time_data_ucd': dic['ucds'][time_axis],
                              'time_data': numpy.array(dic[dic['ordered_column_names'][time_axis]])})
                    input_dic['srcid'] = self.sdict.get("src_id",0) # 20110611 dstarr added just for lightcurve.py:lomb_code():<Plot the PSD(freq)> debug/allstars-plot use.
                    #input_dic.update({})#20110512commentout#'frequencies':self.fgen(input_dic['time_data'])}) # 20110512: NOTE: this and self.frequencies are not used by any current features (used to be related to old lomb implementations).  About to add a new self.frequencies overwriting declaration in lomb_scargle_extractor.py:extractor(), which will allow the first freq self.frequencies, self.psd to be accessible to outside code.
                except:
                    pass
                ## FLUX/MAG AXIS: REQUIRED (or does it? Maybe we just want position versus time. Oh well....)
                flux_or_mag_axis     = 1
                try:
                    input_dic.update({'flux_data_unit': dic['units'][flux_or_mag_axis],
                              'flux_data_ucd': dic['ucds'][flux_or_mag_axis],\
                    'flux_data': numpy.array(dic[dic['ordered_column_names'][flux_or_mag_axis]])})
                except:
                    input_dic.update({'flux_data': numpy.array([])})

                ## UNCERTAINTY IN FLUX/MAX: OPTIONAL
                try:
                    flux_or_mag_err_axis = self.reckon_err_axis(dic,flux_or_mag_axis)
                    if flux_or_mag_err_axis:
                        input_dic.update({'rms_data_unit': dic['units'][flux_or_mag_err_axis],
                                  'rms_data_ucd': dic['ucds'][flux_or_mag_err_axis],
                                  'rms_data': numpy.array(dic[dic['ordered_column_names'][flux_or_mag_err_axis]])})
                    else:
                        ## assume that the UCD and units are the same as the flux axis
                        input_dic.update({'rms_data_unit': dic['units'][flux_or_mag_axis],
                                  'rms_data_ucd': dic['ucds'][flux_or_mag_axis], \
                                  'rms_data': nominal_flux_or_mag_err*numpy.ones((len(input_dic['time_data'])))})
                except:
                    pass
                ## POSITIONAL INFORMATION: OPTIONAL
                ##    positional info will have a UCD like pos.something.something
                pos_header_names = [x for x in dic['ucds'][1:] if x.find("pos.") != -1]
                if len(pos_header_names) in [2,4]:
                    print("FUTURE: There appears to be time_dependent positional information passed. You'll want to load input_dict with this.")
                else:
                    print("        NOTE: No apparent time depdendent position information passes to from_xml().")

            else:
                ## warning!
                ## TODO: this is volitile because 1) we might not require m_err and 2) the name of the flux and time axes could be different
                if "t" in dic:
                    time = numpy.array(dic['t'])
                else:
                    time = numpy.array([])

                input_dic.update({'time_data': time, 'flux_data':numpy.array(dic['m']), 'rms_data':numpy.array(dic['m_err']), \
                    'frequencies':self.fgen(time)})

            input_dic.update( {'ra':self.sdict['ra'], 'dec':self.sdict['dec'], 'ra_rms':self.sdict['ra_rms'], 'dec_rms':self.sdict['dec_rms']})
            # 20090616 added:
            input_dic['limit_mag_dict'] = dic.get('limitmags',{}) # 20090624 c/o dic['limitmags']
        self.signalgen['source']='xml'
        self.signaldata['multiband'] = {}
        input_dic = self.sub_dics(self.signaldata['multiband'])
        input_dic.update( {'ra':self.sdict['ra'], 'dec':self.sdict['dec'], 'ra_rms':self.sdict['ra_rms'], 'dec_rms':self.sdict['dec_rms']}) # copied from line 28


    def fgen(self, time_data):
        #var = { 'x': noisetime, 'y': noisedata, 'ylabel': 'Amplitude', 'xlabel':'Time (s)' }

        N= len(time_data)

        if N > 1:
            # NOTE: 20090717: dstarr replaces frequency definition with freq defs from lightcurve.py->get_out_dict()
            #maxt = max(time_data)
            #mint = min(time_data)
            #dt = (maxt - mint)/N #findAverageSampleTime(var,0)
            #maxlogx = log(1/(2*dt)) # max frequency is the sampling rate
            #minlogx = log(1/(maxt-mint)) #min frequency is 1/T
            #frequencies = exp(arange(N, dtype = float) / (N-1.) * (maxlogx-minlogx)+minlogx)

            ### 20091122:
            #tt = time_data - min(time_data)
            #fmin = 0.5/max(tt)
            #fmax = 48 # 48cyc/day : this cooresponds to 30 minute period, a minimum period of interest.    #n0 / (2.*max(tt))
            #df_over_f=0.001
            #numf = long( ceil( log(fmax/fmin)/df_over_f ) )
            #freqin = exp( log(fmax)-log(fmax/fmin)*arange(numf, dtype=float)/(numf-1.) )
            #om = 2.*pi*freqin
            #frequencies = om/(2.*pi)
            ###

            tt = time_data - min(time_data)
            fmin = 0.5/max(tt)
            fmax = 48 # 48cyc/day : this cooresponds to 30 minute period, a minimum period of interest.    #n0 / (2.*max(tt))

            df = 0.1/max(tt)
            numf = long( ceil( (fmax-fmin)/df ) )
            num_freq_max=10000

            if (numf>num_freq_max):
                numf = num_freq_max
                df = (fmax - fmin)/numf
                freqin = fmax - df*arange(numf,dtype=float)

                om = 2.*pi*freqin
                frequencies = om/(2.*pi)
        else:
            frequencies = numpy.array([1])

        return frequencies

