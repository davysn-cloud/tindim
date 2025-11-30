-- Configuração do Supabase Storage para áudios
-- Execute este script no Supabase SQL Editor após criar o bucket 'audio-digests'

-- 1. Criar política para permitir upload de áudios (service role)
CREATE POLICY "Service role can upload audio files"
ON storage.objects FOR INSERT
TO service_role
WITH CHECK (bucket_id = 'audio-digests');

-- 2. Criar política para leitura pública dos áudios
CREATE POLICY "Public can read audio files"
ON storage.objects FOR SELECT
TO public
USING (bucket_id = 'audio-digests');

-- 3. Criar política para service role deletar arquivos antigos
CREATE POLICY "Service role can delete audio files"
ON storage.objects FOR DELETE
TO service_role
USING (bucket_id = 'audio-digests');

-- Nota: Você também pode configurar isso pela interface do Supabase:
-- Storage > audio-digests > Policies
-- E marcar como "Public bucket" se quiser acesso totalmente público
