from decimal import Decimal

import pytest

from modules.token_usage.application.record_token_usage import RecordTokenUsageUseCase


class _FakeResponse:
    def __init__(self, usage_metadata=None):
        self.usage_metadata = usage_metadata


class _FakeRepository:
    def __init__(self, raise_on_save: Exception | None = None):
        self.saved = []
        self._raise_on_save = raise_on_save

    def save(self, record):
        if self._raise_on_save:
            raise self._raise_on_save
        self.saved.append(record)


def _use_case(repository):
    return RecordTokenUsageUseCase(
        repository,
        price_per_1k_input=Decimal("0.27"),
        price_per_1k_output=Decimal("1.10"),
    )


def test_execute_monta_registro_correto_a_partir_do_usage_metadata():
    repo = _FakeRepository()
    use_case = _use_case(repo)
    response = _FakeResponse(usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})

    use_case.execute(
        response=response,
        tenant_id="tenant_x",
        base_thread_id="tenant_x:sessao_1",
        thread_id="tenant_x:sessao_1#abc",
        node_type="operational_node",
    )

    assert len(repo.saved) == 1
    record = repo.saved[0]
    assert record.tenant_id == "tenant_x"
    assert record.base_thread_id == "tenant_x:sessao_1"
    assert record.node_type == "operational_node"
    assert record.input_tokens == 100
    assert record.output_tokens == 50
    assert record.total_tokens == 150
    assert record.estimated_cost_usd > 0


def test_execute_sem_usage_metadata_nao_lanca_e_registra_com_zeros():
    repo = _FakeRepository()
    use_case = _use_case(repo)
    response = _FakeResponse(usage_metadata=None)

    use_case.execute(
        response=response,
        tenant_id="tenant_x",
        base_thread_id="tenant_x:sessao_1",
        thread_id=None,
        node_type="chitchat_node",
    )

    assert len(repo.saved) == 1
    assert repo.saved[0].input_tokens == 0
    assert repo.saved[0].output_tokens == 0
    assert repo.saved[0].estimated_cost_usd == Decimal("0.000000")


def test_execute_sem_base_thread_id_nao_persiste_registro_orfao():
    repo = _FakeRepository()
    use_case = _use_case(repo)
    response = _FakeResponse(usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})

    use_case.execute(
        response=response,
        tenant_id="tenant_x",
        base_thread_id=None,
        thread_id=None,
        node_type="routing_agent",
    )

    assert repo.saved == []


def test_execute_falha_do_repositorio_nao_propaga(caplog):
    """FR-006: falha ao persistir nunca pode afetar a resposta ao cliente."""
    repo = _FakeRepository(raise_on_save=RuntimeError("Postgres indisponível"))
    use_case = _use_case(repo)
    response = _FakeResponse(usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})

    # Não deve levantar exceção nenhuma.
    use_case.execute(
        response=response,
        tenant_id="tenant_x",
        base_thread_id="tenant_x:sessao_1",
        thread_id=None,
        node_type="operational_node",
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
