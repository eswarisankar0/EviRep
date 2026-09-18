
import pandas as pd
pre = pd.read_csv('data/clinical_maturity_precutoff.csv')
post = pd.read_csv('data/ground_truth_postcutoff.csv')
print('Unique compounds PRE-cutoff:', pre['compound_id'].nunique())
print('Unique compounds POST-cutoff (positives):', post['compound_id'].nunique())
print()
print(post['phase'].value_counts())
print()
print('--- Sample of 15 post-cutoff compounds ---')
print(post[['compound_name','nct_id','phase','status']].drop_duplicates('compound_name').head(15).to_string())
