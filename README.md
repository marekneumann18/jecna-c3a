# ⚡ Ječná Suplování & Discord Notifikátor pro C3a

Tento projekt řeší nepřehledné luštění obří excelovské tabulky na školním SharePointu SPŠE Ječná. V reálném čase sleduje změny a suplování pro třídu **C3a** a automaticky odesílá upozornění do tvého Discord kanálu. Navíc obsahuje moderní a přehledné webové rozhraní optimalizované pro mobil i počítač.

---

## 🚀 Rychlé spuštění

Projekt nevyžaduje žádné složité instalace ani externí knihovny – běží na čistém Pythonu 3!

1. Přejdi do složky s projektem:
   ```bash
   cd /home/mark/.gemini/antigravity/scratch/jecna-supl-c3a
   ```

2. Spusť server:
   ```bash
   python3 server.py
   ```

3. Otevři v prohlížeči:
   👉 **[http://localhost:8080](http://localhost:8080)**

---

## 🔔 Jak nastavit notifikace na Discord

1. Na svém Discord serveru (nebo v soukromém kanálu) klikni na **ozubené kolečko** u kanálu ➡️ **Integrace** (*Integrations*).
2. Zvol **Webhooks** ➡️ **Nový webhook** (*New Webhook*).
3. Pojmenuj ho třeba `Suplování C3a` a klikni na **Kopírovat adresu URL webhooku** (*Copy Webhook URL*).
4. Otevři webové rozhraní `http://localhost:8080`, klikni nahoře na **Discord zprávy**, vlož URL adresu a klikni na **Uložit**.
5. Můžeš rovnou kliknout na tlačítko **🧪 Otestovat zprávu na Discord**, abys viděl, jak zpráva vypadá.

Jakmile vedení školy nahraje nebo upraví suplování pro C3a, bot ti okamžitě pošle zprávu do Discordu!

---

## 🌟 Co všechno systém umí

- **Sledování třídy C3a v reálném čase**: Monitoruje jak konkrétní změny v 1.–10. vyučovací hodině (odpadlé hodiny, suplování, přesuny učeben), tak celodenní akce a exkurze zapsané v poznámkách (např. *C3a - exkurze Ústav informatiky*).
- **Discord Embedy**: Bohatě formátované zprávy s barvami podle stavu (zelená = bez změn, oranžová = příprava, modrá/červená = suplování/odpadlá hodina), přesnými časy zvonění a seznamem chybějících učitelů.
- **Detekce změn bez spamu**: Bot si pamatuje stav každého dne a zprávu pošle jen tehdy, když dojde k reálné změně nebo zveřejnění nového dne.
- **Responzivní Web Dashboard**: Přehledná mřížka všech 10 hodin se zvoněním, filtry dnů (Dnes, Zítra, Příprava), seznam chybějících profesorů a akcí školy.
- **Nulové závislosti**: Využívá vestavěný Python `http.server` a `urllib`.

---

## ⚙️ Běh na pozadí (Daemon / Autostart)

Pokud chceš nechat monitor běžet neustále na pozadí:

### Možnost A: Přes `nohup` (jednoduché)
```bash
nohup python3 server.py > server.log 2>&1 &
```

### Možnost B: Pomocí `systemd` služby (např. na domácím serveru / VPS)
Vytvoř soubor `/etc/systemd/system/jecna-supl.service`:
```ini
[Unit]
Description=Jecna Suplovani C3a Monitor
After=network.target

[Service]
Type=simple
User=mark
WorkingDirectory=/home/mark/.gemini/antigravity/scratch/jecna-supl-c3a
ExecStart=/usr/bin/python3 /home/mark/.gemini/antigravity/scratch/jecna-supl-c3a/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
A zapni službu:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jecna-supl.service
```
