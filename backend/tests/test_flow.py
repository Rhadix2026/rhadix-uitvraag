"""Integratietests voor de KIK-opvraag-flow."""


def test_health(client):
    assert client.get("/api/health").status_code == 200


def test_login_werkt(auth):
    assert "Authorization" in auth


def test_acht_profielen(client, auth):
    profs = client.get("/api/profielen", headers=auth).json()
    assert len(profs) == 8
    assert all("aantal_indicatoren" in p for p in profs)
    detail = client.get(f"/api/profielen/{profs[0]['key']}", headers=auth).json()
    assert len(detail["indicatoren"]) == profs[0]["aantal_indicatoren"]


def test_onbekend_profiel_404(client, auth):
    assert client.get("/api/profielen/bestaat-niet", headers=auth).status_code == 404


def test_zorgaanbieder_registratie_en_lijst(client, auth):
    # demo-aanbieders zijn geseed
    za = client.get("/api/zorgaanbieders", headers=auth).json()
    assert len(za) >= 3
    # publieke zelfregistratie (zonder token)
    r = client.post("/api/zorgaanbieders/register",
                    json={"naam": "Testaanbieder X", "plaats": "Zwolle"})
    assert r.status_code == 201, r.text
    # dubbele naam -> 400
    assert client.post("/api/zorgaanbieders/register",
                       json={"naam": "Testaanbieder X"}).status_code == 400


def test_uitvraag_flow_met_export(client, auth):
    profs = client.get("/api/profielen", headers=auth).json()
    key = profs[0]["key"]
    codes = [i["code"] for i in client.get(f"/api/profielen/{key}", headers=auth).json()["indicatoren"]]
    za = client.get("/api/zorgaanbieders", headers=auth).json()
    ids = [z["id"] for z in za[:2]]

    r = client.post("/api/uitvragen", headers=auth,
                    json={"profiel_key": key, "indicator_codes": codes, "zorgaanbieder_ids": ids})
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["aantal_antwoorden"] == len(codes) * 2
    assert u["status"] in ("VOLTOOID", "GEDEELTELIJK", "MISLUKT")

    # detail
    det = client.get(f"/api/uitvragen/{u['id']}", headers=auth).json()
    assert len(det["antwoorden"]) == len(codes) * 2

    # exports
    csv_r = client.get(f"/api/uitvragen/{u['id']}/export.csv", headers=auth)
    assert csv_r.status_code == 200 and "Zorgaanbieder" in csv_r.text
    xlsx_r = client.get(f"/api/uitvragen/{u['id']}/export.xlsx", headers=auth)
    assert xlsx_r.status_code == 200 and len(xlsx_r.content) > 1000


def test_auth_handhaving(client):
    assert client.get("/api/uitvragen").status_code == 401


def test_ongeldige_indicator_422(client, auth):
    profs = client.get("/api/profielen", headers=auth).json()
    za = client.get("/api/zorgaanbieders", headers=auth).json()
    r = client.post("/api/uitvragen", headers=auth, json={
        "profiel_key": profs[0]["key"], "indicator_codes": ["BESTAAT_NIET"],
        "zorgaanbieder_ids": [za[0]["id"]]})
    assert r.status_code == 422


def test_stats_endpoint(client, auth):
    profs = client.get("/api/profielen", headers=auth).json()
    key = profs[0]["key"]
    codes = [i["code"] for i in client.get(f"/api/profielen/{key}", headers=auth).json()["indicatoren"]]
    za = [z["id"] for z in client.get("/api/zorgaanbieders", headers=auth).json()[:2]]
    client.post("/api/uitvragen", headers=auth,
                json={"profiel_key": key, "indicator_codes": codes, "zorgaanbieder_ids": za})

    r = client.get("/api/uitvragen/stats", headers=auth)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["totaal_uitvragen"] >= 1
    assert s["totaal_antwoorden"] >= len(codes) * 2
    assert set(s["antwoord_status"]) == {"OK", "GEEN_DATA", "FOUT"}
    assert 0.0 <= s["response_ratio"] <= 1.0
    assert "gemiddeld_ms" in s["doorlooptijd"]
    assert len(s["per_profiel"]) >= 1
    assert len(s["per_zorgaanbieder"]) >= 1
    # 'stats' mag niet als uitvraag-id worden gelezen
    assert client.get("/api/uitvragen/stats", headers=auth).status_code == 200


def test_capabilities_overzicht(client, auth):
    d = client.get("/api/capabilities/overzicht", headers=auth).json()
    assert d["totaal"] >= 10
    assert d["status_telling"].get("productie", 0) >= 1
    assert len(d["per_profiel"]) >= 1 and len(d["per_aanbieder"]) >= 1


def test_capabilities_filter_productie(client, auth):
    prod = client.get("/api/capabilities/profiel/igj-toezicht", headers=auth).json()
    assert all(a["status"] == "productie" for a in prod["aanbieders"])
    incl = client.get("/api/capabilities/profiel/igj-toezicht?inclusief_niet_productie=true", headers=auth).json()
    assert len(incl["aanbieders"]) >= len(prod["aanbieders"])


def test_capabilities_import_csv(client, auth):
    goed = ("aanbieder_id_type,aanbieder_id,aanbieder_naam,software_leverancier,uitwisselprofiel,versie,status,laatst_bijgewerkt\n"
            "kvk,30112233,Zorggroep De Linden,Nedap,igj-toezicht,1.0,productie,2026-03-01\n"
            "kvk,98,Foute BV,X,igj-toezicht,1.0,onzin,2026-03-01\n")
    r = client.post("/api/capabilities/import", headers=auth, files={"file": ("up.csv", goed, "text/csv")})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["verwerkt"] == 1 and s["afgekeurd"] == 1
    # formaatfout -> hele bestand afgekeurd (422)
    bad = client.post("/api/capabilities/import", headers=auth, files={"file": ("x.csv", "kolomA,kolomB\n1,2", "text/csv")})
    assert bad.status_code == 422
    # zonder token -> 401
    assert client.post("/api/capabilities/import", files={"file": ("x.csv", "a,b\n1,2", "text/csv")}).status_code == 401


def test_profielen_refresh_admin(client, auth):
    r = client.post("/api/profielen/refresh", headers=auth)
    assert r.status_code == 200, r.text
    assert "bron" in r.json() and r.json()["profielen"] >= 1
    # zonder token -> 401
    assert client.post("/api/profielen/refresh").status_code == 401


def test_external_kikstarter_api(client, auth):
    # OAuth2 password-grant token
    r = client.post("/api/external/token", data={
        "grant_type": "password", "username": "admin@rhadix.nl",
        "password": "Rhadixvalidatie26!", "client_id": "ksapi"})
    assert r.status_code == 200, r.text
    xtok = r.json()["access_token"]
    XH = {"Authorization": f"Bearer {xtok}"}

    # maak een uitvraag voor Zorggroep De Linden (kvk 30112233 via registry)
    profs = client.get("/api/profielen", headers=auth).json()
    key = profs[0]["key"]
    codes = [i["code"] for i in client.get(f"/api/profielen/{key}", headers=auth).json()["indicatoren"][:2]]
    za = client.get("/api/zorgaanbieders", headers=auth).json()
    linden = [z["id"] for z in za if z["naam"] == "Zorggroep De Linden"][0]
    client.post("/api/uitvragen", headers=auth,
                json={"profiel_key": key, "indicator_codes": codes, "zorgaanbieder_ids": [linden]})

    # vragen ophalen per KVK
    v = client.get("/api/external/vragen?aanbiederIdType=kvk&aanbiederId=30112233", headers=XH).json()
    assert v["aantal"] >= 1
    qid = v["vragen"][0]["query_id"]

    # resultaten ophalen per query_id
    r2 = client.get(f"/api/external/vraag/{qid}/resultaten", headers=XH).json()
    assert r2["aantal"] >= 1 and "waarde" in r2["resultaten"][0]

    # foutpaden
    assert client.post("/api/external/token", data={"grant_type": "x", "username": "a", "password": "b"}).status_code == 400
    assert client.get("/api/external/vragen?aanbiederId=30112233").status_code == 401
