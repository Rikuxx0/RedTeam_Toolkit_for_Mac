# Empire (optional)

`compose.yaml` pins `bcsecurity/empire:v7.0.2` and binds the API and Starkiller to `127.0.0.1:1337` (`/index.html`). It does not start automatically. The image was not pulled during this change.

```sh
docker compose -f c2/empire/compose.yaml config --quiet
docker compose -f c2/empire/compose.yaml up -d
docker compose -f c2/empire/compose.yaml ps
docker compose -f c2/empire/compose.yaml exec empire ./ps-empire client
docker compose -f c2/empire/compose.yaml stop
```

Starkiller is served at `http://127.0.0.1:1337/index.html`. The Compose file binds only to localhost. Image download happens when Compose is explicitly started if the image is absent.

The named volume `redteam-empire_empire-data` holds server data. Stop the service before a consistent backup. The following example uses a locally available `alpine:3.20` image; pull that small utility image explicitly first if needed.

```sh
docker compose -f c2/empire/compose.yaml stop
mkdir -p c2/empire/backups
docker run --rm --pull never -v redteam-empire_empire-data:/data:ro -v "$PWD/c2/empire/backups:/backup" alpine:3.20 sh -c 'cd /data && tar -czf /backup/empire-data.tgz .'
docker volume create redteam-empire-restore_empire-data
docker run --rm --pull never -v redteam-empire-restore_empire-data:/data -v "$PWD/c2/empire/backups:/backup:ro" alpine:3.20 sh -c 'cd /data && tar -xzf /backup/empire-data.tgz'
```

Record the Empire image tag with the archive. Test the restored volume under a separate Compose project (`docker compose -p redteam-empire-restore -f c2/empire/compose.yaml up -d --pull never`) while the original is stopped. The original volume remains untouched. Never use `docker compose down -v` here. Change default credentials before operational use. `.env` is ignored by Git; use `.env.example` as a template.

The upstream image Dockerfile uses SQLite by default. Additional databases require a separate compatibility review. Listener reachability and agent connections remain unverified.
