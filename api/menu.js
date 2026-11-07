/**
 * api/menu.js - Vercel Serverless Function (Node.js)
 * Fetches iCanteen lunch menu, cleans food titles, fetches high-res images,
 * and responds with JSON (GET /api/menu or GET /api/menu?date=YYYY-MM-DD).
 */

const https = require('https');

const DEFAULT_URL = 'https://strav.nasejidelna.cz/0341/login';
const DEFAULT_PRICE = '40.00 Kč';
const DEFAULT_LOCATION = 'Ječná';

function fetchUrl(url) {
  return new Promise((resolve, reject) => {
    https.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8'
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

function cleanFoodQuery(rawName) {
  let name = rawName.replace(/[\(\[\{][^\)\]\}]*[\)\]\}]/g, ' ');
  name = name.replace(/\b\d+\s*(?:g|dkg|kg|ks|porce|ml|l)\b/gi, ' ');
  const parts = name.split(/[,/;+]/).map(p => p.trim()).filter(Boolean);
  if (!parts.length) return 'jídlo oběd';

  const soupKeywords = ['polévka', 'vývar', 'krém', 'čočková', 'bramboračka', 'gulášová', 'hrachová', 'zeleninová', 'hovězí', 'slepičí', 'rybí', 'kaldoun', 'uzená', 'celerová', 'krupicí'];
  let target = parts[0];
  if (parts.length > 1) {
    const isSoup = soupKeywords.some(kw => parts[0].toLowerCase().includes(kw));
    if (isSoup) {
      target = parts.length >= 3 ? `${parts[1]} ${parts[2]}` : parts[1];
    } else {
      target = `${parts[0]} ${parts[1]}`;
    }
  }
  target = target.replace(/[^\w\s\u00C0-\u017F-]/g, ' ').replace(/\s+/g, ' ').trim();
  return `${target} jídlo`;
}

async function searchDishImage(mealName) {
  const query = cleanFoodQuery(mealName);
  try {
    const bingUrl = `https://www.bing.com/images/search?q=${encodeURIComponent(query)}&form=HDRSC2&first=1`;
    const html = await fetchUrl(bingUrl);
    const matches = [...html.matchAll(/murl&quot;:&quot;(https?:\/\/[^&]+)&quot;/g)].map(m => m[1]);
    for (const m of matches) {
      if (/\.(jpg|jpeg|png|webp)/i.test(m) || m.includes('photo') || m.includes('upload')) {
        return m;
      }
    }
    if (matches.length > 0) return matches[0];
  } catch (e) {
    console.error('Image search failed:', e);
  }
  return 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80';
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const queryDate = req.query && req.query.date ? req.query.date : null;
  const canteenUrl = req.query && req.query.url ? req.query.url.replace('nasajdelna.cz', 'nasejidelna.cz').replace('/3341/', '/0341/') : DEFAULT_URL;

  try {
    const html = await fetchUrl(canteenUrl);
    const dayRegex = /<div id="day-(\d{4}-\d{2}-\d{2})".*?<\/article>/gs;
    const days = [];
    let match;

    while ((match = dayRegex.exec(html)) !== null) {
      const dateStr = match[1];
      const dayBlock = match[0];

      const titleM = dayBlock.match(/<div id="day-\d{4}-\d{2}-\d{2}"[^>]*>(.*?)<\/div>/s);
      const formattedDate = titleM ? titleM[1].replace(/<.*?>|&nbsp;/g, ' ').replace(/\s+/g, ' ').trim() : '';

      const containers = dayBlock.split('<div class="container">').slice(1);
      const meals = [];

      for (const c of containers) {
        const locM = c.match(/<(?:span|div)[^>]*>(Sokolská|Štěpánská|Ječná)<\//);
        const location = locM ? locM[1] : '';
        if (location && !location.includes(DEFAULT_LOCATION)) continue;

        const numM = c.match(/Oběd\s*(\d+)/);
        const mealNum = numM ? numM[1] : '1';

        const colM = c.match(/<div class="column jidelnicekItem.*?>(.*?)<\/div>/s);
        if (!colM) continue;

        const rawCol = colM[1];
        const allergens = [];
        const algRegex = /title="([^"]+)">(\d+)<\/span>/g;
        let algM;
        while ((algM = algRegex.exec(rawCol)) !== null) {
          allergens.push({ code: algM[2], description: algM[1] });
        }

        const cleanedHtml = rawCol.replace(/<sub>.*?<\/sub>/gs, '').replace(/<.*?>/g, ' ').replace(/\s+/g, ' ').trim();
        if (!cleanedHtml) continue;

        const imageUrl = await searchDishImage(cleanedHtml);

        meals.push({
          id: `obid-${mealNum}`,
          name: cleanedHtml,
          imageUrl: imageUrl,
          price: DEFAULT_PRICE,
          category: `Oběd ${mealNum}`,
          location: location || DEFAULT_LOCATION,
          allergens: allergens
        });
      }

      if (meals.length > 0) {
        days.push({
          date: dateStr,
          formattedDate: formattedDate,
          meals: meals
        });
      }
    }

    if (queryDate) {
      const found = days.find(d => d.date === queryDate);
      return res.status(200).json(found || { date: queryDate, meals: [] });
    }

    return res.status(200).json(days);
  } catch (error) {
    console.error('Menu scraping error:', error);
    return res.status(500).json({ error: error.message });
  }
};
