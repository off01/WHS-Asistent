"""One fresh Edge browser per processing run."""


def open_browser(url, options, service):
    from selenium import webdriver
    try:
        driver = webdriver.Edge(options=options, service=service)
    except Exception as error:
        message = getattr(error, 'msg', str(error)).split('Stacktrace:', 1)[0].strip()
        raise RuntimeError('Edge se nepodařilo spustit: ' + ' '.join(message.split())) from error
    try:
        driver.get(url)
    except BaseException:
        try:
            driver.quit()
        except Exception:
            pass
        raise
    return driver
