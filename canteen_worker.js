/**
 * canteen_worker.js - Cloudflare Workers handler for iCanteen Menu
 * Deploy freely with `wrangler deploy` or copy-paste into Cloudflare Workers Dashboard.
 */

const DEFAULT_URL = 'https://strav.nasejidelna.cz/0341/login';
const DEFAULT_PRICE = '40.00 Kč';
const DEFAULT_LOCATION = 'Ječná';

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
    const resp = await fetch(bingUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'cs-CZ,cs;q=0.9'
      }
    });
    const html = await resp.text();
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

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, OPTIONS',
          'Access-Control-Allow-Headers': '*'
        }
      });
    }

    if (url.pathname === '/api/menu' || url.pathname === '/') {
      const targetDate = url.searchParams.get('date');
      const targetUrl = url.searchParams.get('url') ? url.searchParams.get('url').replace('nasajdelna.cz', 'nasejidelna.cz').replace('/3341/', '/0341/') : DEFAULT_URL;

      try {
        const resp = await fetch(targetUrl, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
          }
        });
        const html = await resp.text();

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

        const resultData = targetDate ? (days.find(d => d.date === targetDate) || { date: targetDate, meals: [] }) : days;

        return new Response(JSON.stringify(resultData, null, 2), {
          headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 's-maxage=1800, max-age=1800'
          }
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
          }
        });
      }
    }

    return new Response('Not found', { status: 404 });
  }
};
