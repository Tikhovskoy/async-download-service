import asyncio
import logging
import os

from aiohttp import web
import aiofiles


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def archive(request):
    archive_hash = request.match_info['archive_hash']
    archive_path = os.path.join('test_photos', archive_hash)

    if not os.path.exists(archive_path):
        raise web.HTTPNotFound(text='Архив не существует или был удален')

    response = web.StreamResponse()
    response.headers['Content-Type'] = 'application/zip'
    response.headers['Content-Disposition'] = f'attachment; filename="{archive_hash}.zip"'
    await response.prepare(request)

    process = await asyncio.create_subprocess_exec(
        'zip', '-r', '-', '.',
        cwd=archive_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    try:
        chunk_size = 65536
        while True:
            chunk = await process.stdout.read(chunk_size)
            if not chunk:
                break
            logger.info('Отправляю chunk архива ...')
            await response.write(chunk)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info('Загрузка была прервана')
        raise
    except ConnectionResetError:
        logger.info('Клиент отключился')
        raise
    except Exception as e:
        logger.error(f'Ошибка при создании архива: {e}')
        raise
    finally:
        if process.returncode is None:
            logger.warning(f'Убиваю процесс zip с PID {process.pid}')
            process.kill()
            await process.communicate()

    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


if __name__ == '__main__':
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archive),
    ])
    web.run_app(app)
