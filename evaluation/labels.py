# Independent labels written from reading the raw resume text BEFORE comparing to pipeline output.
# E = clearly eligible (genuine Python AND a real LLM/RAG/agent/embedding project/experience entry)
# B = borderline (arguable either way)   M = Python but only classical ML/CV or no ML   N = clearly ineligible
LABEL = {}
for n in "06 07 08 10 12 13 16 17 19 22 23 24 25 26 28 29 30 33 35 36 37 38 39 40 41 43 44 47 49 50".split(): LABEL[n]="E"
for n in "03 09 15 34".split(): LABEL[n]="B"
for n in "04 05 14 20 21 48".split(): LABEL[n]="M"
for n in "01 02 11 18 27 31 32 42 45 46".split(): LABEL[n]="N"
assert len(LABEL)==50
# quality tier among clearly-eligible: A strong agentic/RAG depth, B solid but narrower, C thin/modest
TIER = {}
for n in "07 12 13 16 17 22 28 30 33 35 41 43 47".split(): TIER[n]=3
for n in "08 10 19 23 37 39 40 44 50".split(): TIER[n]=2
for n in "06 24 25 26 29 36 38 49".split(): TIER[n]=1
assert set(TIER)=={k for k,v in LABEL.items() if v=="E"}
