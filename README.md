# ⚡ Ječná Suplování & Rozvrh C3a

Moderní webová aplikace a Discord notifikátor pro třídu **C3a** na SPŠE Ječná.  
Funguje jak lokálně, tak **zcela zdarma v cloudu na GitHub Pages & GitHub Actions** bez nutnosti mít zapnutý vlastní počítač!

---

## 📱 Jak nahrát stránku na GitHub a dívat se na ni kdekoli (mobil / PC)

Tato stránka je navržena tak, že **funguje přímo na GitHub Pages** jako samostatná webová aplikace. Nemusíš mít spuštěný žádný server – web si stahuje data ze školy přímo z prohlížeče!

### 1. Vytvoření repozitáře na GitHubu
1. Jdi na [github.com/new](https://github.com/new) a přihlas se.
2. Pojmenuj repozitář třeba `jecna-c3a` (nech ho Public) a klikni na **Create repository**.

### 2. Nahrání kódu (stačí zadat do terminálu)
V terminálu spusť (nahraď `TVUJ_GITHUB_USERNAME`):
```bash
cd /home/mark/.gemini/antigravity/scratch/jecna-supl-c3a
git remote add origin https://github.com/TVUJ_GITHUB_USERNAME/jecna-c3a.git
git push -u origin main
```

### 3. Zapnutí GitHub Pages (aby byla stránka online)
1. Ve svém repozitáři na GitHubu klikni nahoře na **Settings** (Ozubené kolečko).
2. V levém menu klikni na **Pages**.
3. V sekci **Build and deployment** vyber:
   - Source: **Deploy from a branch**
   - Branch: **`main`** / Folder: **`/ (root)`**
4. Klikni na **Save**.
5. Během 1–2 minut bude tvá stránka live na adrese:  
   👉 **`https://TVUJ_GITHUB_USERNAME.github.io/jecna-c3a/`**

Můžeš si ji otevřít na mobilu a dokonce přidat na plochu jako aplikaci (PWA)!

---

## 🔔 Automatické Discord notifikace přes GitHub Actions (zcela zdarma)

Chceš, aby ti chodily zprávy o suplování na Discord, i když máš vypnutý počítač?  
V repozitáři je připravený automatický workflow `.github/workflows/discord-notifier.yml`.

1. V repozitáři na GitHubu jdi do **Settings** ➡️ **Secrets and variables** ➡️ **Actions**.
2. Klikni na zelené tlačítko **New repository secret**.
3. Do pole **Name** zadej: `DISCORD_WEBHOOK_URL`
4. Do pole **Secret** vlož svou URL adresu Discord webhooku.
5. Klikni na **Add secret**.

Hotovo! GitHub Actions bude od pondělí do pátku každých 30 minut automaticky kontrolovat suplování pro C3a a v případě změn ti pošle zprávu do Discordu.

---

## 💻 Lokální spuštění na počítači (volitelné)

Pokud chceš aplikaci provozovat lokálně:
```bash
python3 server.py 8080
```
Otevři: **[http://localhost:8080](http://localhost:8080)**

---

## 📚 Vysvětlivky předmětů C3a

- **PV:** Programové vybavení
- **WA:** Webové aplikace
- **DS:** Databázové systémy
- **PSS:** Počítačové sítě a systémy
- **CIT:** Cvičení z informatiky
- **MVH:** Multimedia a vývoj her
- **EK:** Ekonomika
- **TI:** Teoretická informatika
- **C:** Český jazyk
- **M:** Matematika
- **A:** Anglický jazyk
- **TV:** Tělesná výchova
