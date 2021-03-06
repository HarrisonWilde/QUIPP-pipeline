import os
import pandas as pd
import pytest
import sys
import numpy as np
from ctgan.synthesizer import CTGANSynthesizer as ctgan_original_model_class

sys.path.append(os.path.join(os.path.dirname(__file__), os.path.pardir))
from ctgan_main import SynthesizerCTGAN

# Fixed inputs for tests
path2csv = os.path.join("synth-methods", "CTGAN", "tests", "data", "test_CTGAN_io.csv")
path2meta = os.path.join("synth-methods", "CTGAN", "tests", "data", "test_CTGAN_io_data.json")
path2params = os.path.join("synth-methods", "CTGAN", "tests", "parameters", "ctgan_parameters.json")
dataset_name = 'test_CTGAN_io'

output_path = "./synthetic-output/dataset-name"

inp_discrete_columns = ['id', 'age', 'origin', 'favourite_food']
dis_dim = (256, 256)
gen_dim = (256, 256)
embed_dim = 128
batch_size = 500
num_epochs = 2
random_state = 1234

num_samples_to_synthesize = 200
num_samples_to_fit = -1

age2integer = {
        '0-17': 0,
        '18-24': 1,
        '25-44': 2,
        '45-64': 3,
        '65-84': 4,
        '85-': 5
    }

@pytest.fixture
def ctgan_syn():
    ctgan_syn = SynthesizerCTGAN()
    return ctgan_syn

def test_SynthesizerCTGAN_init(ctgan_syn):
    assert ctgan_syn.discrete_column_names == None, "discrete_column_names is not instantiated!"

def test_SynthesizerCTGAN_fit_synthesizer(ctgan_syn):
    ctgan_syn.fit_synthesizer(path2params, path2csv, path2meta)
    assert isinstance(ctgan_syn.model, ctgan_original_model_class)
    assert ctgan_syn.model.dis_dim == dis_dim, "Unexpected discriminative dimensions %s" % dis_dim
    assert ctgan_syn.model.gen_dim == gen_dim, "Unexpected generatove dimensions %s" % gen_dim
    assert ctgan_syn.model.embedding_dim == embed_dim, "Unexpected embedding dimension: %s" % embed_dim
    assert ctgan_syn.discrete_column_names == inp_discrete_columns, "Discrete columns do not match!"
    assert ctgan_syn.num_epochs == num_epochs, "Unexpected number of epochs %s" % num_epochs
    assert ctgan_syn.random_state == random_state, "Unexpected random state %s" %  random_state
    assert ctgan_syn.num_samples_to_fit == num_samples_to_fit, "Unexpected number of samples to fit %s" % num_samples_to_fit
    assert ctgan_syn.model.batch_size == batch_size, "Unexpected batch size: %s" % batch_size

def test_SynthesizerCTGAN_synthesize(ctgan_syn):
    ctgan_syn.fit_synthesizer(path2params, path2csv, path2meta)
    ctgan_syn.synthesize(output_path=output_path, num_samples_to_synthesize=num_samples_to_synthesize, store_internally=True)
    assert ctgan_syn.dataset_name == dataset_name, "Unexpected dataset name: %s" % dataset_name
    assert ctgan_syn.num_samples_to_synthesize == num_samples_to_synthesize, "Unexpected num_samples_to_synthesize: %s" %num_samples_to_synthesize
    assert os.path.isfile(os.path.join(output_path,"synthetic_data_1.csv")), "File %s is not created!" % output_path
    assert os.path.isdir("./synthetic-output/dataset-name"), "Directory is not created"
    assert os.path.isdir("./synthetic-output"), "Directory is not created"
    read_csv_file = pd.read_csv(os.path.join(output_path,"synthetic_data_1.csv"))
    assert len(read_csv_file) ==  num_samples_to_synthesize, "Number of rows in the generated CSV file is not equal to num_samples_to_synthesize: %s" % num_samples_to_synthesize

def test_SynthesizerCTGAN_correlation(ctgan_syn):
    path2csv = os.path.join("datasets", "generated", "odi_nhs_ae", "hospital_ae_data_deidentify.csv")
    path2meta = os.path.join("datasets", "generated", "odi_nhs_ae", "hospital_ae_data_deidentify.json")
    path2params = os.path.join("synth-methods", "CTGAN", "tests", "parameters", "ctgan_parameters_corr.json")
    dataset_name = 'test_CTGAN_corr'
    output_path = f"./synthetic-output/{dataset_name}"

    num_samples_to_synthesize = 10000

    ctgan_syn.fit_synthesizer(path2params, path2csv, path2meta)
    ctgan_syn.synthesize(output_path=output_path, num_samples_to_synthesize=num_samples_to_synthesize,
                         store_internally=False)

    synth = pd.read_csv(os.path.join(output_path,"synthetic_data_1.csv"))
    synth = synth.replace({"Age bracket": age2integer})
    synth_corr = synth.corr().iloc[3, 0]

    real = pd.read_csv(path2csv)
    real = real.replace({"Age bracket": age2integer})
    real_corr = real.corr().iloc[3, 0]

    # test currently doesn't make any real evaluation on quality of the synthesizer
    assert np.abs(synth_corr - real_corr / np.abs(real_corr)) < 10,\
        f"Correlation between age band and A&E time differs between synthetic and real data sets (more than 10%): " \
        f"synthetic: {synth_corr}, real: {real_corr}"
    #import ipdb; ipdb.set_trace()



