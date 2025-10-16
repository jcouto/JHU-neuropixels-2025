from pathlib import Path
import os
import numpy as np
from os.path import join as pjoin
from tqdm import tqdm
from glob import glob
import pandas as pd

###############################################################################
################# HANDLE RAW BINARY FILES #####################################
###############################################################################

def map_binary(fname,nchannels,dtype=np.int16,
               offset = 0,
               mode = 'r',nsamples = None,transpose = False):
    ''' 
    dat = map_binary(fname,nchannels,dtype=np.int16,mode = 'r',nsamples = None)
    
Memory maps a binary file to numpy array.
    Inputs: 
        fname           : path to the file
        nchannels       : number of channels
        dtype (int16)   : datatype
        mode ('r')      : mode to open file ('w' - overwrites/creates; 'a' - allows overwriting samples)
        nsamples (None) : number of samples (if None - gets nsamples from the filesize, nchannels and dtype)
    Outputs:
        data            : numpy.memmap object (nchannels x nsamples array)
See also: map_spikeglx, numpy.memmap

    Usage:
Plot a chunk of data:
    dat = map_binary(filename, nchannels = 385)
    chunk = dat[:-150,3000:6000]
    
    import pylab as plt
    offset = 40
    fig = plt.figure(figsize=(10,13)); fig.add_axes([0,0,1,1])
    plt.plot(chunk.T - np.nanmedian(chunk,axis = 1) + offset * np.arange(chunk.shape[0]), lw = 0.5 ,color = 'k');
    plt.axis('tight');plt.axis('off');

    Joao Couto 2019
    '''
    dt = np.dtype(dtype)
    if not os.path.exists(fname):
        if not mode == 'w':
            raise(ValueError('File '+ fname +' does not exist?'))
        else:
            print('Does not exist, will create [{0}].'.format(fname))
            if not os.path.isdir(os.path.dirname(fname)):
                os.makedirs(os.path.dirname(fname))
    if nsamples is None:
        if not os.path.exists(fname):
            raise(ValueError('Need nsamples to create new file.'))
        # Get the number of samples from the file size
        nsamples = os.path.getsize(fname)/(nchannels*dt.itemsize)
    ret = np.memmap(fname,
                    mode=mode,
                    dtype=dt,
                    shape = (int(nsamples),int(nchannels)))
    if transpose:
        ret = ret.transpose([1,0])
    return ret

def read_spikeglx_meta(metafile):
    '''
    Read spikeGLX metadata file.

    Joao Couto - 2019
    '''
    with open(metafile,'r') as f:
        meta = {}
        for ln in f.readlines():
            try:
                tmp = ln.split('=')
                k,val = tmp
                k = k.strip()
                val = val.strip('\r\n')
            except:
                print(f'Skipping {tmp}')
                continue
            if '~' in k:
                meta[k.strip('~')] = val.strip('(').strip(')').split(')(')
            else:
                try: # is it numeric?
                    meta[k] = float(val)
                except:
                    try:
                        meta[k] = float(val) 
                    except:
                        meta[k] = val
    # Set the sample rate depending on the recording mode
    meta['sRateHz'] = meta[meta['typeThis'][:2]+'SampRate']
    try:
        parse_coords_from_spikeglx_metadata(meta)
    except:
        pass
    return meta

def parse_coords_from_spikeglx_metadata(meta,shanksep = 250):
    '''
    Python version of the channelmap parser from spikeglx files.
    Adapted from the matlab from Jennifer Colonell

    Joao Couto - 2022
    '''
    if not 'imDatPrb_type' in meta.keys():
        meta['imDatPrb_type'] = 0.0 # 3A/B probe
    probetype = int(meta['imDatPrb_type'])
    shank_sep = 250

    imro = np.stack([[int(i) for i in m.split(' ')] for m in meta['imroTbl'][1:]])
    chans = imro[:,0]
    banks = imro[:,1]
    shank = np.zeros(imro.shape[0])
    connected = np.stack([[int(i) for i in m.split(':')] for m in meta['snsShankMap'][1:]])[:,3]
    if (probetype <= 1) or (probetype == 1100) or (probetype == 1300):
        # <=1 3A/B probe
        # 1100 UHD probe with one bank
        # 1300 OPTO probe
        electrode_idx = banks*384 + chans
        if probetype == 0:
            nelec = 960;    # per shank
            vert_sep  = 20; # in um
            horz_sep  = 32;
            pos = np.zeros((nelec, 2))
            # staggered
            pos[0::4,0] = horz_sep/2       # sites 0,4,8...
            pos[1::4,0] = (3/2)*horz_sep   # sites 1,5,9...
            pos[2::4,0] = 0;               # sites 2,6,10...
            pos[3::4,0] = horz_sep         # sites 3,7,11...
            pos[:,0] = pos[:,0] + 11          # x offset on the shank
            pos[0::2,1] = np.arange(nelec/2) * vert_sep   # sites 0,2,4...
            pos[1::2,1] = pos[0::2,1]                    # sites 1,3,5...

        elif probetype == 1100:   # HD
            nelec = 384      # per shank
            vert_sep = 6    # in um
            horz_sep = 6
            pos = np.zeros((nelec,2))
            for i in range(7):
                ind = np.arange(i,nelec,8)
                pos[ind,0] = i*horz_sep
                pos[ind,1] = np.floor(ind/8)* vert_sep
        elif probetype == 1300: #OPTO
            nelec = 960;    # per shank
            vert_sep  = 20; # in um
            horz_sep  = 48;
            pos = np.zeros((nelec, 2))
            # staggered
            pos[0:-1:2,0] = 0          # odd sites
            pos[1:-1:2,0] = horz_sep   # even sites
            pos[0:-1:2,1] = np.arange(nelec/2) * vert_sep
    elif probetype == 24 or probetype == 21:
        electrode_idx = imro[:,2]
        if probetype == 24:
            banks = imro[:,2]
            shank = imro[:,1]
            electrode_idx = imro[:,4]
        nelec = 1280       # per shank; pattern repeats for the four shanks
        vert_sep  = 15     # in um
        horz_sep  = 32
        pos = np.zeros((nelec, 2))
        pos[0::2,0] = 0                              # x pos
        pos[1::2,0] = horz_sep
        pos[1::2,0] = pos[1::2,0] 
        pos[0::2,1] = np.arange(nelec/2) * vert_sep   # y pos sites 0,2,4...
        pos[1::2,1] = pos[0::2,1]                     # sites 1,3,5...
    else:
        print('ERROR [parse_coords_from_spikeglx_metadata]: probetype {0} is not implemented.'.format(probetype))
        raise NotImplementedError('Not implemented probetype {0}'.format(probetype))
    coords = np.vstack([shank*shank_sep+pos[electrode_idx,0],
                        pos[electrode_idx,1]]).T    
    idx = np.arange(len(coords))
    meta['coords'] = coords[connected==1,:]
    meta['channel_idx'] = idx[connected==1]
    return idx,coords,connected

def load_spikeglx_binary(fname, dtype=np.int16):
    ''' 
    data,meta = load_spikeglx_binary(fname,nchannels)
    
    Memory maps a spikeGLX binary file to numpy array.

    Inputs: 
        fname           : path to the file
    Outputs:
        data            : numpy.memmap object (nchannels x nsamples array)
        meta            : meta data from spikeGLX

    Joao Couto - 2019
    '''
    name = os.path.splitext(fname)[0]
    ext = '.meta'

    metafile = name + ext
    if not os.path.isfile(metafile):
        raise(ValueError('File not found: ' + metafile))
    meta = read_spikeglx_meta(metafile)
    nchans = meta['nSavedChans']
    return map_binary(fname,nchans,dtype=np.int16,mode = 'r'),meta


def list_spikeglx_files(folder):
    '''
    A function to list (multiprobe) spikeglx files.
    
    apfiles,nidqfile = list_spikeglx_files(folder)
    
    Joao Couto - CSHL Ion Channels course 2023
    '''
    niqdfile = glob(pjoin(folder,'*.nidq.bin'),recursive = True)
    if len(niqdfile): niqdfile = niqdfile[0] 
    apfiles = np.sort(glob(pjoin(folder,'*','*.ap.bin'),recursive = True))
    #raise an error if the folder did not have probe files
    if not len(apfiles):
        raise(OSError('There were no probe files in folder '+ folder))
    return apfiles,niqdfile

###############################################################################
################# HANDLE SYNCHRONIZATION AND THE SYNC BYTES ###################
###############################################################################

def unpackbits(x,num_bits = 16):
    '''
    unpacks numbers in bits.

    Joao Couto - April 2019
    '''
    xshape = list(x.shape)
    x = x.reshape([-1,1])
    to_and = 2**np.arange(num_bits).reshape([1,num_bits])
    return (x & to_and).astype(bool).astype(int).reshape(xshape + [num_bits])


def unpack_npix_sync(syncdat,srate=1,output_binary = False):
    '''Unpacks neuropixels phase external input data
events = unpack_npix3a_sync(trigger_data_channel)    
    Inputs:
        syncdat               : trigger data channel to unpack (pass the last channel of the memory mapped file)
        srate (1)             : sampling rate of the data; to convert to time - meta['imSampRate']
        output_binary (False) : outputs the unpacked signal
    Outputs
        events        : dictionary of events. the keys are the channel number, the items the sample times of the events.

    Joao Couto - April 2019

    Usage:
Load and get trigger times in seconds:
    dat,meta = load_spikeglx('test3a.imec.lf.bin')
    srate = meta['imSampRate']
    onsets,offsets = unpack_npix_sync(dat[:,-1],srate);
Plot events:
    plt.figure(figsize = [10,4])
    for ichan,times in onsets.items():
        plt.vlines(times,ichan,ichan+.8,linewidth = 0.5)
    plt.ylabel('Sync channel number'); plt.xlabel('time (s)')
    '''
    dd = unpackbits(syncdat.flatten(),16)
    mult = 1
    if output_binary:
        return dd
    sync_idx_onset = np.where(mult*np.diff(dd,axis = 0)>0)
    sync_idx_offset = np.where(mult*np.diff(dd,axis = 0)<0)
    onsets = {}
    offsets = {}
    for ichan in np.unique(sync_idx_onset[1]):
        onsets[ichan] = sync_idx_onset[0][
            sync_idx_onset[1] == ichan]/srate
    for ichan in np.unique(sync_idx_offset[1]):
        offsets[ichan] = sync_idx_offset[0][
            sync_idx_offset[1] == ichan]/srate
    return onsets,offsets

###############################################################################
############################ LOAD PHY DATA ####################################
###############################################################################

def waveforms_position(
    waveforms,
    channel_positions,
    active_electrode_threshold=3,
    max_waveform_extent=100,
    ):
    '''Calculates the position of a unit in a set of channels using the center of mass.
Considers only electrodes that have over active_electrode_threshold (3) mad and 
are within max_waveform_extent (100um) from the principal (max) electrode.

Using the max_waveform_extent is useful when there is noise in the recording. 

centerofmass,peak_channels = waveforms_position(waveforms,channel_positions)

Inputs
------
waveforms : array [ncluster x nsamples x nchannels]
    average waveform for a cluster 
channel_positions : array [nchannels x 2]
    x and y coordinates of each channel

Return
-------
centerofmass: array [nchannels x 2]
    center of mass of the waveforms 
peak_channels array [nchannels x 1]
    peak channel of the waveform (the argmax of the absolute amplitude)

Joao Couto - spks 2023
    '''
    nclusters, nsamples, nchannels = waveforms.shape
    N = int(nsamples/4)
    peak_to_peak = waveforms.max(axis=1) - waveforms.min(axis=1)
    # get the threshold from the median_abs_deviation
    channel_mad = np.median(peak_to_peak/0.6745, axis = 1)
    active_electrodes = []
    center_of_mass = []
    peak_channels = []
    for i,w in enumerate(peak_to_peak):
        peak_channels.append(np.argmax(w)) # the peak channel is the index of the channel that has the largest deflection
        idx = np.where(
            (w>(channel_mad[i]*active_electrode_threshold)) & 
            (np.linalg.norm(channel_positions - channel_positions[np.argmax(w)],axis = 1) < max_waveform_extent))[0]
        active_electrodes.append(idx)
        if not len(idx): # then there are no active channels..
            center_of_mass.append([np.nan]*2)
            continue
        # compute the center of mass (X,Y) of the waveforms using only significant peaks
        com = [w[idx]*pos for pos in channel_positions[idx].T]
        center_of_mass.append(np.sum(com,axis = 1)/np.sum(w[idx]))
    return np.array(center_of_mass), np.array(peak_channels), active_electrodes 
    return np.array(center_of_mass), np.array(peak_channels), active_electrodes

def compute_spike_amplitudes(templates,whitening_matrix,spike_templates,spike_template_amplitudes, channel_positions):
    '''
    Compute the amplitude of each spike from the template fitting
    '''

    templates_raw = np.dot(templates,whitening_matrix)
    # compute the peak to peak of each template
    templates_peak_to_peak = (templates_raw.max(axis = 1) - templates_raw.min(axis = 1))
    # the amplitude of each template is the max of the peak difference for all channels
    templates_amplitude = templates_peak_to_peak.max(axis=1)
    templates_amplitude = templates_amplitude.copy()
    # Fix for when kilosort returns NaN templates, make them the average of all templates
    templates_amplitude[~np.isfinite(templates_amplitude)] = np.nanmean(templates_amplitude)
    # compute the center of mass (X,Y) of the templates
    template_position,template_channel, electrode_channels = waveforms_position(templates_raw, channel_positions)
    # get the spike positions and amplitudes from the average templates
    spike_amplitudes = np.take(templates_amplitude,spike_templates)*spike_template_amplitudes
    return spike_amplitudes

def estimate_spike_positions_from_features(spike_templates,spike_pc_features,template_pc_features_ind,channel_positions,consider_feature=0):
    '''
    Estimates the spike 2d location based on a feature e.g the PCs.
    
    This is adapted from the cortexlab/spikes repository to estimate spikes based on the PC features.

    Parameters
    ----------
    spike_templates: nspikes x templates used for each spike
    spike_pc_features: nspikes x nfeatures x nchannels
    template_pc_features_ind: indice of the channels for the templates nchannels
    channel_positions: position of each channel
    consider_feature: feature to consider

    Returns
    -------
    spike_locations: nspikes

    Joao Couto - spks 2023
    '''
    # channel index for each feature
    feature_channel_idx = np.take(template_pc_features_ind,spike_templates.flatten().astype(int),axis=0)
    # 2d coordinates for each channel feature
    feature_coords = np.take(channel_positions,feature_channel_idx.flatten().astype(int),axis=0).reshape([*feature_channel_idx.shape,*channel_positions.shape[1:]])
    # ycoords of those channels?
    pc_features = spike_pc_features[:,consider_feature].squeeze()**2 # take the first pc for the features
    spike_locations = (np.sum(feature_coords.transpose((2,0,1))*pc_features,axis=2)/np.sum(pc_features,axis=1)).T
    return spike_locations

def load_phy_folder(folder):
    # we load the results in a dictionary so we don't accidentally confuse results from different sessions
    res = dict(
        # spiketimes and other
        spike_times = np.load(folder.rglob('spike_times.npy').__next__()),
        spike_clusters = np.load(folder.rglob('spike_clusters.npy').__next__()),
        spike_templates = np.load(folder.rglob('spike_templates.npy').__next__()),
        pc_features = np.load(folder.rglob('pc_features.npy').__next__()),
        pc_feature_ind = np.load(folder.rglob('pc_feature_ind.npy').__next__()),
        spike_template_amplitudes = np.load(folder.rglob('amplitudes.npy').__next__()),
        # metrics for each cluster
        metrics = pd.read_csv(folder.rglob('metrics.csv').__next__()),
        # waveforms
        channel_indices = np.load(folder.rglob('channel_map.npy').__next__()),
        channel_positions = np.load(folder.rglob('channel_positions.npy').__next__()),
        mean_waveforms = np.load(folder.rglob('mean_waveforms.npy').__next__()),
        templates = np.load(folder.rglob('templates.npy').__next__()),
        whitening_mat_inv = np.load(folder.rglob('whitening_mat_inv.npy').__next__())
    )

    # estimate the amplitudes from the template fitting
    res['spike_amplitudes'] = compute_spike_amplitudes(templates = res['templates'],
                                                    whitening_matrix= res['whitening_mat_inv'],
                                                    spike_templates = res['spike_templates'],
                                                    spike_template_amplitudes = res['spike_template_amplitudes'],
                                                    channel_positions = res['channel_positions'])
    # estimate the positions from the template fitting features
    res['spike_positions'] = estimate_spike_positions_from_features(spike_templates=res['spike_templates'],
                                        spike_pc_features = res['pc_features'],
                                        template_pc_features_ind = res['pc_feature_ind'],
                                        channel_positions = res['channel_positions'])
    return res

###############################################################################
#################     DOWNLOAD RAW DATA   #####################################
###############################################################################

def download_dataset(dataset_name, output_path = None):
    if dataset_name in  ['help','info']:
        print('''
        
    USAGE: download_dataset(dataset_name,output_path)

Available datasets:
    - chronic_stimulus
    - chronic_sorting_output
    - chronic_raw

You can also access the datasets here: https://drive.google.com/drive/folders/1NgLJcoTkgbn2edV8MfLVVbLhEMJn8JfC?usp=share_link

-------------------------------------
    Dataset chronic_stimulus:
-------------------------------------
Downloads the stimulus times and phy output for the chronic dataset included in Steinmetz et al. 2021
This is an individual shank of a 4 shank probe implanted in mouse V1 - recordings by Anna Lebedeva and Michael Okun in the cortex lab at UCL (M. Carandini and K. Harris).
The data was taken from AL032, shank0 only, recording day 2019-11-21

AL032/AL032_stimulus_times.mat was extracted from the original data provided by UCL, using Anna's code for alignment of the flipper signal in the SYNC channel of these data. For each day,  there is a list of stimulus identities (individual natural images, 1-112), time in seconds, and time in milliseconds, for each of 5 trials. The events.csv file included in the file of KS4 output was derived from this file using the included script.
This dataset was prepared by Jennifer Colonell (HHMI Janelia) 

-------------------------------------
    Dataset chronic_sorting_output:
-------------------------------------
Preprocessed binary + sorting output, from the ecephys_spike_sorting pipeline, running KS4
This dataset was prepared by Jennifer Colonell (HHMI Janelia) 

This is an individual shank of a 4 shank probe implanted in mouse V1 - recordings by Anna Lebedeva and Michael Okun in the cortex lab at UCL (M. Carandini and K. Harris).
The data was taken from AL032, shank0 only, recording day 2019-11-21

-------------------------------------
    Dataset chronic_raw:
-------------------------------------
This is an individual shank of a 4 shank probe implanted in mouse V1 - recordings by Anna Lebedeva and Michael Okun in the cortex lab at UCL (M. Carandini and K. Harris).
The data was taken from AL032, shank0 only, recording day 2019-11-21

Raw binary + metadata, exported from the original binary provided by UCL (Thanks to Anna Lebedeva for help getting the original files).
This dataset was prepared by Jennifer Colonell (HHMI Janelia)

        ''')
        return
    if dataset_name == 'chronic_stimulus':
        file_list = dict(AL032_stimulus = '1ecWZdG-xjWCNq37hop1Go1__WkxVv5Lo',
                         AL032_out = '1ko94OPRynre9AsTwHvTTiNbuK7dtZSRJ',)
    elif dataset_name == 'chronic_sorting_output':
        file_list = dict(AL032_out = '1ko94OPRynre9AsTwHvTTiNbuK7dtZSRJ')
    elif dataset_name == 'chronic_raw':
        file_list = dict(AL032 = '16asaS_ZAxxQk8iYlptyPWl3BTr0tcW0Y')
    else:
        raise(ValueError(f'Unknown dataset {dataset_name}.'))
    try:
        from gdown import download
    except ImportError:
        print('\n\n\n gdown is not installed. will attempt to install it now...\n\n\n')
        import os
        os.system('pip install gdown')
        from gdown import download

    from pathlib import Path
    import zipfile

    if output_path is None:
        output_path = '.'
    output_path = Path(output_path).absolute()

    for k in file_list.keys():
        if not (output_path/k).exists():
            (output_path/k).mkdir(parents=True)
        else:
            print(f'Path {output_path/k} is there; delete it if you want to download the dataset again.')    
        zippath = output_path/k/f'{k}.zip'
        download(id = file_list[k], output = str(zippath))

        folderpath = output_path/k/f'{k}'
        with zipfile.ZipFile(str(zippath), 'r') as zf:
            zf.extractall(output_path)


def plot_drift_raster(spiketimes,spikepositions,spikeamplitudes, n_spikes_to_plot = 200000,cmap = 'Spectral_r',clim=[0,10000],markersize = 0.3):
    import pylab as plt

    plt.figure(figsize = [12,4])

    # randomly subsample n_spikes_to_plot spikes
    subsample = np.random.choice(np.arange(len(spiketimes),dtype=int),n_spikes_to_plot,replace = False)

    # sort by the amplitude so the color is seen
    subsample = subsample[np.argsort(spikeamplitudes[subsample])]

    spikes = spiketimes[subsample]

    plt.scatter(spikes,
                spikepositions[subsample][:,1],
                markersize,
                spikeamplitudes[subsample],
                clim=clim, 
                cmap = cmap)

    plt.ylim([spikepositions[subsample][:,1].min(),spikepositions[subsample][:,1].max()])
    plt.xlim([spikes.min(),spikes.max()])