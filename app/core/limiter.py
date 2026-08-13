# LINHAS DE ALTERAÇÃO - CRIAÇÃO DO ARQUIVO DE LIMITER
# COMENTÁRIO DUMMY: Este arquivo isola a criação do Limiter. 
# Como nem o main.py e nem o chat.py dependem um do outro aqui, a referência cíclica é quebrada.

from slowapi import Limiter
from slowapi.util import get_remote_address

# Instância única compartilhada por toda a aplicação
limiter = Limiter(key_func=get_remote_address)