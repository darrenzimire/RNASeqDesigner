# encoding =UTF-8

import os
import numpy as np
import gzip
from itertools import chain
from Bio.Seq import Seq
import pyfaidx
from SequenceContainer import ReadContainer
from process_inputFiles import process_countmodel
import random
import distributions
import argparse
import process_models


def get_arguments():
	tool_description = 'This tool creates a position-wise distribution of quality values from a fastq file ' \
	                   'It creates a .qmodel.p file which can be passed to RSDS to simulate Phred quality scores.'

	parser = argparse.ArgumentParser(description=tool_description)

	parser.add_argument('-r', type=int, required=False, default=101, help='Read length')
	parser.add_argument('-n', type=int, required=False, help='Number of reads to simulate')
	parser.add_argument('-f', type=str, required=False, help='Reference transcriptome file')
	parser.add_argument('-s', type=int, required=False, default=1223,
	                    help='Random seed for reproducibility')
	parser.add_argument('-o', type=str, required=False, help='Output prefix')
	parser.add_argument('-q', type=str, required=False, help='Sequencing_model')
	parser.add_argument('-c', type=str, required=False,
	                    help='transcript expression count model')
	parser.add_argument('-er', type=float, required=False, default=-1, help='Error rate')
	parser.add_argument('-FLdist', nargs=2, type=int, required=False, default=(250, 25),
	                    help='Fragment length distribution parameters')
	parser.add_argument('-FLmodel', type=str, required=False)
	parser.add_argument('-SE', action='store_true', required=False, help='Flag for producing single-end reads ')
	parser.add_argument('-PE', action='store_true', required=False, help='Flag for producing paired-end reads')

	return parser


argparser = get_arguments()
args = argparser.parse_args()

(fragment_size, fragment_std) = args.FLdist
FLmodel = args.FLmodel
ref = args.f
readlen = args.r
readtot = args.n
SEED = args.s
output = args.o
sqmodel = args.q
countModel = args.c
SE_RATE = args.er

print('reading reference file: ' + str(ref) + "\n")

pyfaidx.Faidx(ref)
print('Indexing reference file....' + "\n")

indexFile = ''
for file in os.listdir('.'):
	if file.endswith('.fai'):
		indexFile = (os.path.join('.', file))


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
	fai = open(indexFile, 'r')
	for line in fai:
		splt = line[:-1].split('\t')
		header = '@' + splt[0]
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


def samplingtranscripts(ids):
	""""
	Description: This function randomly sample from all reference transcripts
	Parameters: ids (list of tuples) It takes as input all reference transcripts offsets
	Returns: This function returns a subset of transcript ids to be sampled from
	"""
	random.seed(seed)
	numreads = readtot
	sampledtranscripts = random.sample(ids, numreads)

	return sampledtranscripts


def scalereadnum(read_counts, n):
	sc = []
	scale = []
	total = sum(read_counts)
	for i in read_counts:
		x = i / total
		scale.append(x)
	for i in scale:
		y = n * i
		sc.append(round(y))
	scaled_counts = [1 if x == 0 else x for x in sc]

	return scaled_counts


def getseq(key, start=1, end=None):
	"""
	Description
	Get a sequence by key coordinates are 1-based and end is inclusive
	Parameters:
		key:
		start:
		end:
	Returns:
	"""

	if end != None and end < start:
		return ""
	start -= 1
	seek = start

	# if seek is past sequence then return empty sequence
	if seek >= end:
		return ""

	# seek to beginning
	infile = open(ref, 'r')
	infile.seek(seek)

	# read until end of sequence
	header = ''
	seq = []
	if end == None:
		lenNeeded = util.INF
	else:
		lenNeeded = end - start

	len2 = 0
	while len2 < lenNeeded:
		line = infile.readline()
		if line.startswith(">") or len(line) == 0:
			break
		seq.append(header + line.rstrip())
		len2 += len(seq[-1])
		if len2 > lenNeeded:
			seq[-1] = seq[-1][:-int(len2 - lenNeeded)]
			break
	seq = "".join(seq)
	return seq


def processTransIDs(ids):
	""""
	Description:
	This function take as input a list of transcript ids and converts it to a dictionary
	Parameters:
		ids (list of tuples): List of transcript ids
	Returns: The function returns a dictionary of transcript id as key and start and end position as value
	"""

	Transseq = []
	header = []
	transcriptID = {i: [j, k] for i, j, k in ids}
	ID = transcriptID.keys()
	for k in ID:
		header.append(k)
	pos = transcriptID.values()
	for i in pos:
		start = i[0]
		end = i[1]
		seq = getseq(ID, start, end)
		Transseq.append(seq)

	new_dict = {k: v for k, v in zip(header, Transseq)}
	return new_dict


def GenerateRead(seq, readLen, n, *args):
	"""
	Description:
	This function truncates transcript sequences by a specified read length.
	Parameters:
	:param seq: Transcript sequence randomly sampled from the input reference transcriptome file
	:param readLen: The user-specified read length

	:return: The function returns a list of all truncated sequences
	"""

	seqLen = len(seq)
	spos = []
	epos = []

	for ag in args:

		if ag == 'SE':

			nmax = seqLen - readLen - 1
			v = np.round(np.random.uniform(low=0, high=nmax, size=None))
			startpos = list(random.choices(v, k=n))
			endpos = [i + readLen for i in startpos]
			spos.append(startpos)
			epos.append(endpos)

		elif ag == 'PE':

			nmax = [seqLen - i - 1 for i in readLen]
			v = np.round(np.random.uniform(low=0, high=nmax, size=n))
			startpos = list(random.choices(v, k=len(readLen)))
			endpos = [i + j for i, j in zip(startpos, readLen)]
			spos.append(startpos)
			epos.append(endpos)

	return spos, epos


def reverse_complement(inputread):
	s = Seq(str(inputread))
	read = s.reverse_complement()
	return read


SE_CLASS = ReadContainer(readlen, sqmodel, SE_RATE)


def sample_qualscore(sequencingModel):
	(myQual, myErrors) = SE_CLASS.getSequencingErrors(sequencingModel)

	return myQual


def sequence_identifier(index):
	header = '{}{} {} {}{}'.format('@RSDS_v0.1.', index, index, 'length=', str(readlen))
	return header


def get_reads(record):
	start = record[0]
	end = record[1]
	sequence = record[2]
	reads = []
	for s, e in zip(start, end):
		r = sequence[int(s):int(e)]
		reads.append(r)

	return reads


def process_reads_PE(fragment, index):
	R1 = []
	R2 = []
	prob = str(np.random.rand(1)).lstrip('[').rstrip(']')
	read1 = ''.join(map(str, fragment[:readlen]))
	read2 = str(reverse_complement(fragment[-readlen:]))
	if float(prob) < 0.5:
		R1.append(read2)
		R2.append(read1)

	return R1, R2


def main():
	ref_transcript_ids = parseIndexRef(indexFile)

	NB_counts = distributions.negative_binomial()
	counts_NB = np.random.choice(NB_counts, size=readtot, replace=True).tolist()

	profile_propcount = []
	profile_counts = []
	profile_ids = []
	if args.c:
		profile = process_countmodel(countModel)
		print('detecting profile')
		ids = profile[0]
		counts = profile[1]
		propcount = profile[2]
		profile_ids.append(ids)
		profile_counts.append(counts)
		profile_propcount.append(propcount[0])

	if args.SE:

		sample_trans_ids = []
		COUNTS = []
		ID = []
		Seq = []

		if countModel == None:
			print('Simulating single-end reads....' + "\n")
			print('No transcript profile model detected!!' + "\n")
			print('Simulating default transcript profile' + "\n")
			scaled_counts = scalereadnum(counts_NB, readtot)
			samptransids = random.choices(ref_transcript_ids, k=len(scaled_counts))
			sample_trans_ids.append(samptransids)
			COUNTS.append(scaled_counts)

		elif countModel != None and readtot == None:
			print('Simulating single-end reads....' + "\n")
			print('Detected transcript profile model.....' + "\n")
			print('Simulating empirical transcript profile' + "\n")

			sample_trans_ids.append(profile_ids[0])
			COUNTS.append(profile_counts[0])

		elif countModel != None and readtot != None:
			counts_s = [round(int(i * readtot)) for i in profile_propcount[0]]
			counts_1s = [1 if x == 0 else x for x in counts_s]

			COUNTS.append(counts_1s)
			sample_trans_ids.append(profile_ids[0])
		data = list(chain.from_iterable(sample_trans_ids))

		for j in data:
			p = processTransIDs([j])
			for id, seq in p.items():
				ID.append(id)
				Seq.append(seq)
		with gzip.open(output + '.fastq.gz', 'wb') as handle:
			for seq, r in zip(Seq, COUNTS[0]):
				readinfo = GenerateRead(seq, readlen, r, 'SE')
				startpos = readinfo[0]
				endpos = readinfo[1]
				for index, (i, j) in enumerate(zip(startpos[0], endpos[0])):
					header = sequence_identifier(index)
					read = seq[int(i):int(j)]
					q = sample_qualscore(sequencingModel=sqmodel)
					handle.write('{}\n{}\n+\n{}\n'.format(header, read, q).encode())

	elif args.PE:

		sample_trans_ids = []
		RFS = []
		COUNTS_P = []
		ID = []
		Seq = []
		R1 = []
		R2 = []
		FS = np.random.normal(fragment_size, fragment_std, 100000).astype(int).tolist()

		if countModel == None:
			print('Generating paired-end reads.....' + "\n")
			print('Sampling counts from negative binomial model' + "\n")
			counts_p = scalereadnum(counts_NB, readtot)
			COUNTS_P.append(counts_p)
			sample_trans_ids = random.choices(ref_transcript_ids, k=len(COUNTS_P[0]))

		elif countModel != None and readtot == None:
			print('Generating paired-end reads' + "\n")
			print('Simulating empirical transcript profile.....' + "\n")
			COUNTS_P.append(profile_counts[0])
			sample_trans_ids = profile_ids[0]

		elif countModel != None and readtot != None:
			print('Generating paired-end reads' + "\n")
			print('Simulating empirical transcript profile.....' + "\n")
			counts_p = scalereadnum(profile_propcount[0], readtot)
			COUNTS_P.append(counts_p)
			sample_trans_ids = profile_ids

		for i in COUNTS_P[0]:
			if FLmodel != None:
				randomFS = random.choices(process_models.proc_FLmodel(FLmodel, readtot), k=i)
				RFS.append(randomFS)
				print(randomFS)

			else:
				randomFS = random.choices(FS, k=i)
				RFS.append(randomFS)

		for j in sample_trans_ids:
			p = processTransIDs([j])
			for id, seq in p.items():
				ID.append(id)
				Seq.append(seq)

		for seq, r in zip(Seq, RFS):
			readinfo = GenerateRead(seq, r, len(r), 'PE')
			startpos = readinfo[0]
			endpos = readinfo[1]
			for index, (i, j) in enumerate(zip(startpos[0], endpos[0])):
				read = seq[int(i):int(j)]
				data = process_reads_PE(read, index)
				R1.append(''.join(data[0]))
				R2.append(''.join(data[1]))
		with gzip.open(output + '_R1.fastq.gz', 'wb') as f1, gzip.open(output, '_R2.fastq.gz', 'wb') as f2:
			for index, (i, j) in enumerate(zip(R1, R2)):
				id = sequence_identifier(index)
				q1 = sample_qualscore(sequencingModel=sqmodel)
				f1.write('{}\n{}\n+\n{}\n'.format(id, i, q1).encode())
				q2 = sample_qualscore(sequencingModel=sqmodel)
				f2.write('{}\n{}\n+\n{}\n'.format(id, i, q2).encode())


if __name__ == '__main__':
	main()
