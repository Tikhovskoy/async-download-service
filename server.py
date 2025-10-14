import argparse
import asyncio
import logging
import os

from aiohttp import web
import aiofiles
from dotenv import load_dotenv


logger = logging.getLogger(__name__)


async def archive(request):
    app = request.app
    archive_hash = request.match_info['archive_hash']
    archive_path = os.path.join(app['photos_dir'], archive_hash)

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
        chunk_size = app['chunk_size']
        while True:
            chunk = await process.stdout.read(chunk_size)
            if not chunk:
                break
            logger.info('Отправляю chunk архива ...')
            await response.write(chunk)
            if app['response_delay']:
                await asyncio.sleep(app['response_delay'])
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
    async with aiofiles.open(request.app['index_file'], mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Async file download service')
    parser.add_argument(
        '--logging',
        action='store_true',
        default=os.getenv('LOGGING', 'false').lower() in ('true', '1', 'yes'),
        help='Enable logging (env: LOGGING)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=float(os.getenv('RESPONSE_DELAY', '0')),
        help='Response delay in seconds (env: RESPONSE_DELAY)'
    )
    parser.add_argument(
        '--photos-dir',
        type=str,
        default=os.getenv('PHOTOS_DIR', 'test_photos'),
        help='Path to photos directory (env: PHOTOS_DIR)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.getenv('PORT', '8080')),
        help='Port to run the web server on (env: PORT)'
    )
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=int(os.getenv('CHUNK_SIZE', '65536')),
        help='Chunk size for streaming archives (env: CHUNK_SIZE)'
    )
    parser.add_argument(
        '--index-file',
        type=str,
        default=os.getenv('INDEX_FILE', 'index.html'),
        help='Path to the index HTML file (env: INDEX_FILE)'
    )

    args = parser.parse_args()

    if args.logging:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    app = web.Application()
    app['photos_dir'] = args.photos_dir
    app['response_delay'] = args.delay
    app['chunk_size'] = args.chunk_size
    app['index_file'] = args.index_file

    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archive),
    ])
    web.run_app(app, port=args.port)


if __name__ == '__main__':
    main()
