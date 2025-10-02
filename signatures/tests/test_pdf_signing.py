import os
import io
import base64
from django.test import TestCase
from django.conf import settings
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image

from signatures.utils.pdf_signing import embed_signature


class PDFSigningUtilityTest(TestCase):
    def setUp(self):
        self.media_root = str(settings.MEDIA_ROOT)
        os.makedirs(self.media_root, exist_ok=True)

        # Create a simple one-page PDF to sign
        self.input_pdf_path = os.path.join(self.media_root, 'test_input.pdf')
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        can.drawString(100, 750, "Test PDF for signing")
        can.save()
        packet.seek(0)
        with open(self.input_pdf_path, 'wb') as f:
            f.write(packet.read())

        # Create a small PNG signature image in-memory
        img = Image.new('RGBA', (120, 40), (0, 0, 0, 0))
        # draw a black rectangle to ensure visible content
        for x in range(10, 110):
            for y in range(10, 30):
                img.putpixel((x, y), (0, 0, 0, 255))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        self.signature_b64 = base64.b64encode(img_bytes.read()).decode('utf-8')

        self.output_pdf_path = os.path.join(self.media_root, 'test_output_signed.pdf')

    def tearDown(self):
        for path in [self.input_pdf_path, self.output_pdf_path]:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def test_embed_signature_increases_file_size(self):
        original_size = os.path.getsize(self.input_pdf_path)

        embed_signature(
            pdf_path=self.input_pdf_path,
            output_path=self.output_pdf_path,
            signature_image=self.signature_b64,
            page=1,
            x=100,
            y=100,
            width=120,
            height=40,
        )

        self.assertTrue(os.path.exists(self.output_pdf_path))
        new_size = os.path.getsize(self.output_pdf_path)
        self.assertGreater(new_size, original_size)



