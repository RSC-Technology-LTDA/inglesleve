"""Gera o token permanente da Página do Facebook vinculada ao Instagram e grava nos secrets do GitHub.

1. No Explorador da Graph API (developers.facebook.com/tools/explorer), escolha o app, peça as
   permissões instagram_basic, instagram_content_publish, instagram_manage_insights, pages_show_list,
   pages_read_engagement e business_management, e clique em "Generate Access Token".
2. Rode:  .venv/bin/python tools/ig_token.py --repo RSC-Technology-LTDA/inglesleve
   O script pede o token gerado, o App ID e a chave secreta do app (sem mostrar na tela),
   troca por um token de longa duração, pega o token da Página (que não expira) e grava
   IG_ACCESS_TOKEN e IG_USER_ID nos secrets do repositório via `gh`.
"""

import argparse
import getpass
import subprocess
import sys

import httpx

GRAPH = "https://graph.facebook.com/v23.0"


def get(path: str, **params) -> dict:
    resp = httpx.get(f"{GRAPH}/{path}", params=params, timeout=30)
    data = resp.json()
    if resp.status_code >= 400 or "error" in data:
        sys.exit(f"Erro em {path}: {data.get('error', {}).get('message', resp.text)}")
    return data


def set_secret(repo: str, name: str, value: str) -> None:
    subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value, text=True, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", help="owner/repo para gravar os secrets; sem isso, só mostra os valores")
    ap.add_argument("--app-id", default="1449621164045653")
    args = ap.parse_args()

    short = getpass.getpass("Token do Explorador da Graph API: ").strip()
    secret = getpass.getpass(f"Chave secreta do app {args.app_id}: ").strip()

    long_lived = get(
        "oauth/access_token", grant_type="fb_exchange_token", client_id=args.app_id,
        client_secret=secret, fb_exchange_token=short,
    )["access_token"]

    pages = get(
        "me/accounts", access_token=long_lived,
        fields="name,access_token,instagram_business_account{id,username}",
    ).get("data", [])
    linked = [p for p in pages if p.get("instagram_business_account")]
    if not linked:
        names = ", ".join(p["name"] for p in pages) or "nenhuma"
        sys.exit(f"Nenhuma Página com Instagram vinculado. Páginas encontradas: {names}")

    page = linked[0]
    if len(linked) > 1:
        for i, p in enumerate(linked, 1):
            print(f"{i}. {p['name']} → @{p['instagram_business_account']['username']}")
        page = linked[int(input("Qual usar? ")) - 1]

    ig = page["instagram_business_account"]
    print(f"Página: {page['name']} → Instagram @{ig['username']} (ID {ig['id']})")

    if args.repo:
        set_secret(args.repo, "IG_ACCESS_TOKEN", page["access_token"])
        set_secret(args.repo, "IG_USER_ID", ig["id"])
        print(f"Secrets IG_ACCESS_TOKEN e IG_USER_ID gravados em {args.repo}.")
    else:
        print(f"IG_USER_ID={ig['id']}\nIG_ACCESS_TOKEN={page['access_token']}")


if __name__ == "__main__":
    main()
