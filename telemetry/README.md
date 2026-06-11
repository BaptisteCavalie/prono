# Télémétrie

runs.jsonl : une ligne JSON par session de travail — toute session laisse une trace.
Schéma : {"date","type":"feature|critique|fix|retro","feature","tours","blockers","majors","minors","nits","escalade","dimensions_faibles":[]}
(compteurs critics optionnels hors run de feature)

Usage : observer les tendances, PAS gater. Une dimension faible récurrente
(≥3 runs) = un trou structurel dans un skill → /retro le signale.
