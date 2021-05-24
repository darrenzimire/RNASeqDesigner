# encoding=utf-8

"""
This program takes in a read count expression table, a reference cDNA FASTA database and a file output prefix.
The table is parsed and puts out vector of transcript ids and its associated count in a pickled gzip compressed file.

"""

import argparse
import os
import sys
import pandas as pd
import pickle as pickle
import pyfaidx
import re
import gzip
from rsds import man


def get_arguments():

	parser = argparse.ArgumentParser()

	# parser = argparse.ArgumentParser(description='Tissue_expression_profiler')
	parser.add_argument('-f', type=str, required=True, metavar='<str>', help='reference file')
	parser.add_argument('-c', type=str, required=True, metavar='<str>', help='Count table')
	parser.add_argument('-o', type=str, required=True, metavar='<str>', help='output file prefix')

	return parser


argparser = get_arguments()
args = argparser.parse_args()

refFile = args.f
count_table = args.c
modelName = args.o


def process_readcounts(count_table):
	# Function to filter count table
	# What % of zero values to include as low expressed
	# Sample randomly from table
	# What is the relationship between the zero-values and the values close to zero?
	# How many of the zero values do we want change with respect to the SD?

	df_count_table = pd.read_csv(count_table, sep='\t')
	df1 = df_count_table[df_count_table.IsoPct != 0]
	df1.drop(df1.index)
	read_counts = df1['expected_count'].tolist()

	return read_counts, df1


def parseIndexRef(indexFile):
	"""
	Description:
	Read in sequence data from reference index FASTA file returns a list of transcript IDs
	offset, seqLen, position
	Parameters
	 - indexFile (str): The index file generated by the program, written to the current directory
	Return: The function returns a list of tuples containing the transcript id, start and end offset of the transcript sequence
	"""
	ref_inds = []
	filt_ref_inds = []

	try:

		fai = open(indexFile, 'r')
	except BaseException:

		errlog.error('Cannot find indexed reference file. Please provide a reference FASTA file')
		sys.exit('Cannot find indexed reference file. Please provide a reference FASTA file')

	for line in fai:
		splt = line[:-1].split('\t')
		header = '>' + splt[0]
		seqLen = int(splt[1])
		offset = int(splt[2])
		lineLn = int(splt[3])
		nLines = seqLen / lineLn

		if seqLen % lineLn != 0:
			nLines += 1
		ref_inds.append([header, offset, offset + seqLen + nLines, seqLen])
	for i in ref_inds:
		if i[3] >= 400:
			filt_ref_inds.append(i)
	for x in filt_ref_inds:
		x.pop(3)
	fai.close()

	return filt_ref_inds


def create_model(reference_file):

	df_ref = pd.DataFrame(reference_file, columns=['Transcript_ID', 'start', 'end'])
	df_ref['ENS_transcript_id'] = df_ref['Transcript_ID'].apply(lambda x: re.sub(r"^>(ENST\d*\.\d{1,3})\|.*", r"\1", x))
	table = process_readcounts(count_table)
	df_table = table[1]
	df_result = pd.merge(df_table, df_ref, left_on='transcript_id', right_on='ENS_transcript_id')
	df_result = df_result[['Transcript_ID', 'start', 'end', 'expected_count']]
	total = df_result['expected_count'].sum()
	df_result['proportional_count'] = df_result['expected_count'].div(total)

	return df_result


def main():

	if refFile == None:
		man.manpage()
		sys.exit()

	else:

		basename = str(os.path.basename(modelName))
		os.symlink(refFile, basename)
		pyfaidx.Faidx(basename)
		cwd = os.getcwd()
		indexFile = ''
		for file in os.listdir(cwd):
			if file.endswith('.fai'):
				indexFile = (os.path.join('.', file))

		ref_index = parseIndexRef(indexFile)
		model = create_model(ref_index)
		records = model.to_records(index=False)

		outf = modelName + '_p.gz'
		output = gzip.open(outf, 'wb')
		pickle.dump(records, output)

		os.remove(basename)
		os.remove(indexFile)


if __name__ == '__main__':
	main()
