// Optional local browser check for the synthetic fixture, not a universal page validator.
// Supply an existing Playwright package via NODE_PATH; no installation/download is performed.
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

async function main() {
  const [input, screenshot, reportFile] = process.argv.slice(2).map(value => path.resolve(value));
  if (!input || !screenshot || !reportFile) throw new Error('Usage: node qa/check-format-preview.cjs preview.html screenshot.png report.json');
  if (new Set([input, screenshot, reportFile]).size !== 3) throw new Error('Outputs must differ from input and each other');
  if (fs.existsSync(screenshot) || fs.existsSync(reportFile)) throw new Error('Refusing to overwrite existing outputs');
  const launch = { headless: true };
  if (process.env.HELP_ME_STUDY_BROWSER_EXECUTABLE) launch.executablePath = process.env.HELP_ME_STUDY_BROWSER_EXECUTABLE;
  else if (process.platform === 'win32') launch.channel = 'msedge';
  const browser = await chromium.launch(launch);
  try {
    const context = await browser.newContext({ viewport: { width: 1100, height: 900 }, deviceScaleFactor: 1 });
    await context.route(/^https?:\/\//, route => route.abort());
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.goto(pathToFileURL(input).href, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    const observed = await page.evaluate(() => {
      const copy = document.body.cloneNode(true);
      copy.querySelectorAll('code,pre').forEach(element => element.remove());
      const labels = ['只想了解原流程：', '只是启动项问题：', '只是设备异常：', '准备修改配置：'];
      return {
        title: document.querySelector('h1')?.textContent,
        h2: document.querySelectorAll('h2').length,
        bulletItems: document.querySelectorAll('ul > li').length,
        orderedStart: document.querySelector('ol')?.start,
        orderedItems: document.querySelectorAll('ol > li').length,
        boldLabels: labels.map(text => {
          const element = Array.from(document.querySelectorAll('strong')).find(item => item.textContent === text);
          return { text, weight: element ? Number(getComputedStyle(element).fontWeight) : null };
        }),
        table: Array.from(document.querySelectorAll('table tr'), row => Array.from(row.querySelectorAll('th,td'), cell => cell.textContent)),
        codeProtected: document.querySelector('pre code')?.textContent.includes('result = x**2'),
        sourceSyntaxProtected: document.querySelector('pre code')?.textContent.includes('**语法示例**'),
        imagesLoaded: Array.from(document.images).every(image => image.complete && image.naturalWidth > 0),
        imageCount: document.images.length,
        rawMarkersOutsideCode: copy.textContent.includes('**'),
        horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
        links: Array.from(document.querySelectorAll('a'), link => ({ text: link.textContent, href: link.getAttribute('href') }))
      };
    });
    const expectedTable = [['项目','单位','说明'],['长度','mm','a|b'],['时间','s','记录条件']];
    const passed = observed.title === '笔记格式演练' && observed.h2 === 3 && observed.bulletItems === 4
      && observed.orderedStart === 3 && observed.orderedItems === 2
      && observed.boldLabels.every(item => item.weight >= 600)
      && JSON.stringify(observed.table) === JSON.stringify(expectedTable)
      && observed.codeProtected && observed.sourceSyntaxProtected && observed.imagesLoaded && observed.imageCount === 1
      && !observed.rawMarkersOutsideCode && !observed.horizontalOverflow && pageErrors.length === 0;
    fs.mkdirSync(path.dirname(screenshot), { recursive: true });
    fs.mkdirSync(path.dirname(reportFile), { recursive: true });
    await page.screenshot({ path: screenshot, fullPage: true });
    const report = { passed, observed, pageErrors, screenshot, reportFile,
      scope: 'Synthetic local HTML fixture only; no Notion, Word/PDF or math typesetting verification; remote requests blocked' };
    fs.writeFileSync(reportFile, JSON.stringify(report, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });
    console.log(JSON.stringify(report));
    if (!passed) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 2; });
