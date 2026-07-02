"""
Script simples para testar chamadas da API de eventos
Uso: python test_api.py
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_search_events():
    """Testa busca de eventos externos"""
    print("=== Testando busca de eventos externos ===")
    
    # Testar eventos futuros
    print("\n1. Buscando eventos futuros (Bandsintown):")
    response = requests.get(
        f"{BASE_URL}/events/search/external",
        params={
            "query": "metallica",
            "event_type": "future"
        }
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Source: {data.get('source')}")
        print(f"Total: {data.get('total')}")
        print(f"Eventos encontrados: {len(data.get('events', []))}")
        if data.get('events'):
            print(f"Primeiro evento: {data['events'][0].get('title')}")
    else:
        print(f"Erro: {response.text}")
    
    # Testar eventos passados
    print("\n2. Buscando eventos passados (Setlist.fm):")
    response = requests.get(
        f"{BASE_URL}/events/search/external",
        params={
            "query": "metallica",
            "event_type": "past"
        }
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Source: {data.get('source')}")
        print(f"Total: {data.get('total')}")
        print(f"Eventos encontrados: {len(data.get('events', []))}")
        if data.get('events'):
            first_event = data['events'][0]
            print(f"Primeiro evento: {first_event.get('title')}")
            if first_event.get('setlist'):
                print(f"Setlist: {len(first_event['setlist'])} músicas")
                print(f"Primeiras 3 músicas: {first_event['setlist'][:3]}")
    else:
        print(f"Erro: {response.text}")

def test_get_events():
    """Testa busca de eventos do banco"""
    print("\n=== Testando busca de eventos do banco ===")
    response = requests.get(f"{BASE_URL}/events")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Total de eventos no banco: {len(data)}")
    else:
        print(f"Erro: {response.text}")

if __name__ == "__main__":
    print("Certifique-se de que o servidor está rodando em http://localhost:8000")
    print("Inicie com: python -m uvicorn app.main:app --reload\n")
    
    try:
        test_search_events()
        test_get_events()
        print("\n=== Testes concluídos ===")
    except requests.exceptions.ConnectionError:
        print("\nERRO: Não foi possível conectar ao servidor.")
        print("Certifique-se de que o servidor está rodando.")
    except Exception as e:
        print(f"\nERRO: {e}")
