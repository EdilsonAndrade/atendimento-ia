from modules.agendamento.agente_atendimento import main
def rodar_teste_inicial():
    # Código para iniciar o teste
    print("Iniciando o teste de agente de atendimento...\n")
    servicos = ["Corte de Cabelo", "Manicure", "Pedicure", "Massagem"]
    resposta = main(servicos)
  
    # Assert se resposta contém Corte Cabelo, Manicure, Pedicure, Massagem
    assert "Corte de cabelo".lower() in resposta.lower(), "Resposta não contém 'Corte de cabelo'"
    assert "Manicure".lower() in resposta.lower(), "Resposta não contém 'Manicure'"
    assert "Pedicure".lower() in resposta.lower(), "Resposta não contém 'Pedicure'"
    assert "Massagem".lower() in resposta.lower(), "Resposta não contém 'Massagem'"
    assert "Lavagem de carro".lower() not in resposta.lower(), "Resposta contém 'Lavagem de carro', que não deveria estar presente"
    print("\n----Teste concluído com sucesso----")
    

if __name__ == "__main__":
    rodar_teste_inicial()



