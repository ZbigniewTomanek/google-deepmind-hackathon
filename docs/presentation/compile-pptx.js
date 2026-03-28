const pptxgen = require('pptxgenjs');
const html2pptx = require('./html2pptx.js');
const fs = require('fs');
const path = require('path');

async function compile() {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_16x9';
  pptx.title = 'NeoCortex — Structured Memory for AI Agents';
  pptx.author = 'NeoCortex Team';

  const htmlDir = path.join(__dirname, 'html-slides');
  const outputDir = path.join(__dirname, 'output');

  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const slides = fs.readdirSync(htmlDir)
    .filter(f => f.endsWith('.html'))
    .sort((a, b) => {
      const numA = parseInt(a.match(/slide-(\d+)/)?.[1] || '0');
      const numB = parseInt(b.match(/slide-(\d+)/)?.[1] || '0');
      return numA - numB;
    });

  console.log(`Found ${slides.length} slides to process...`);

  for (const slideFile of slides) {
    console.log(`Processing ${slideFile}...`);
    try {
      await html2pptx(path.join(htmlDir, slideFile), pptx);
    } catch (err) {
      console.error(`Error processing ${slideFile}: ${err.message}`);
      throw err;
    }
  }

  const outputPath = path.join(outputDir, 'neocortex-presentation.pptx');
  await pptx.writeFile({ fileName: outputPath });
  console.log(`Presentation compiled: ${outputPath}`);
}

compile().catch(console.error);
