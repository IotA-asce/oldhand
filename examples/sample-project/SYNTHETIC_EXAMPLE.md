# Synthetic Oldhand demonstration project

Everything in this directory is fictional. It is deliberately small and uses
the reserved `.invalid` domain so it cannot be mistaken for a real service,
credential, or operational system.

The example models a common configuration mistake: an environment file
**replaces** the defaults file rather than merging with it. The accompanying
Oldhand record preserves the constraint that prevents a future agent from
"simplifying" the loader into the same failure.
