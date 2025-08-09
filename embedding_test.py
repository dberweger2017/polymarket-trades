import voyageai

vo = voyageai.Client()

result = vo.embed(["hello world"], model="voyage-3.5")