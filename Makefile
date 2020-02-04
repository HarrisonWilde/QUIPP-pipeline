PYTHON = python

QUIPP_ROOT = $(shell pwd)

RUN_INPUTS = $(wildcard run-input/*.json)
SYNTH_OUTPUTS = $(patsubst $(notdir $(RUN_INPUTS)))

.PHONY: generated-data
generated-data: generator-outputs/odi-nhs-ae/hospital_ae_data_deidentify.csv

generators/odi-nhs-ae/data/London\ postcodes.csv:
	cd generators/odi-nhs-ae/ && \
	curl -o "./data/London postcodes.csv" \
		https://www.doogal.co.uk/UKPostcodesCSV.ashx?region=E12000007

generator-outputs/odi-nhs-ae/hospital_ae_data_deidentify.csv: \
	generators/odi-nhs-ae/data/London\ postcodes.csv
	mkdir -p generator-outputs/odi-nhs-ae/ && \
	cd generator-outputs/odi-nhs-ae/ && \
	$(PYTHON) $(QUIPP_ROOT)/generators/odi-nhs-ae/generate.py

$(SYNTH_OUTPUTS): synth-output/%: run-inputs/%.json generated-data
	python synthesize.py -i $< -o $@
