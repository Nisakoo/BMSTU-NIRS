# Optional backend image dependencies

In the context of one backend image shared by the API and database commands,
facing the download and storage cost of CPU inference, we decided to select
locked speech and hybrid retrieval dependencies at build time. This keeps
the default image and Compose stack small while optional modes require an
image build when their flags change. `make run` selects the speech Compose
file when enabled, and `make migrate` and the lore commands build the image
using the same flags.

See the [Docker guide](../../docker/README.md), [backend Dockerfile](../../docker/Dockerfile),
and [optional dependencies](../../backend/pyproject.toml).
