import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _rodando_dentro_de_container() -> bool:
    """Detecta se o processo está dentro de um container Docker.

    `/.dockerenv` é criado pelo próprio Docker na raiz do container. A checagem em
    /proc/1/cgroup cobre runtimes que não criam esse arquivo.
    """
    if Path("/.dockerenv").exists():
        return True
    try:
        return "docker" in Path("/proc/1/cgroup").read_text()
    except OSError:
        return False


def _normalizar_uri_do_banco() -> None:
    """Traduz `host.docker.internal` para `localhost` quando os testes rodam FORA
    de um container.

    O `.env` do projeto é lido tanto pela aplicação nos containers quanto pelos
    testes na máquina do desenvolvedor, e o endereço correto do Postgres é
    diferente nos dois casos: de dentro do container, a máquina do host é
    `host.docker.internal`; da própria máquina, é `localhost`. Sem esta tradução,
    rodar `pytest` no Windows fazia cada teste de integração esperar o timeout de
    TCP — a suíte parecia travada em vez de falhar.

    Editar o `.env` para `localhost` NÃO é alternativa: dentro do container
    `localhost` é o próprio container, e a API quebraria. Por isso a tradução vive
    aqui, aplicada só quando estamos fora.

    É o mesmo banco nos dois casos — muda apenas como ele é endereçado.
    """
    if _rodando_dentro_de_container():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    uri = os.getenv("POSTGRES_DATABASE_URI")
    if uri and "host.docker.internal" in uri:
        os.environ["POSTGRES_DATABASE_URI"] = uri.replace("host.docker.internal", "localhost")


_normalizar_uri_do_banco()
