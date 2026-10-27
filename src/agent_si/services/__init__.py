"""K06 Lane B services prefix — STEP 2 implementation.

Every services command routes argv-only through the injected Lane A
guard (G1); no shell strings anywhere under this package. The guard is
always supplied by the caller as a callable and never imported from
Lane A code here.
"""
