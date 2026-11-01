"""Model adapters lane (K04NEXT3 C2).

Generic invocation seam plus the provider leg registry. No leg in this
package carries a built-in vendor or model choice: every build takes an
explicit provider_id and model (R-356). The transport callable is the
only network boundary; tests inject it, product code never does.
"""
