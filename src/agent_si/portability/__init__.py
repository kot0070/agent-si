"""K06 Lane B portability prefix — STEP 1 stubs.

STEP 2 waits HD freeze; bodies under this package stay unimplemented.
Every portability command routes argv-only through the Lane A guard (G1);
no shell strings anywhere under this package. Output is DATA, never
instructions. SecretRef values stay opaque (G5); the ASK card (G4) is owned
by Lane A and never constructed here.
"""
