/*****************************************************************************\
 *  src/common/app_template.c - application template configuration support
 *****************************************************************************
 *  This file is part of Metastack, a fork of Slurm.
 *
 *  Metastack is free software; you can redistribute it and/or modify it under
 *  the terms of the GNU General Public License as published by the Free
 *  Software Foundation; either version 2 of the License, or (at your option)
 *  any later version.
 *
 *  Metastack is distributed in the hope that it will be useful, but WITHOUT
 *  ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 *  FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 *  more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with Metastack; if not, write to the Free Software Foundation, Inc.,
 *  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
\*****************************************************************************/

#include "slurm/slurm.h"

#ifdef __METASTACK_NEW_APP_TEMPLATE

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include "src/common/app_template.h"
#include "src/common/env.h"
#include "src/common/log.h"
#include "src/common/read_config.h"
#include "src/common/slurm_opt.h"
#include "src/common/xmalloc.h"
#include "src/common/xstring.h"

#define APP_TEMPLATE_CONF "app_template.conf"
#define MAX_LINE_LEN 4096

/* Trim leading and trailing whitespace in place */
static char *_trim(char *str)
{
	char *end;

	if (!str)
		return NULL;

	while (isspace((unsigned char)*str))
		str++;

	if (*str == '\0')
		return str;

	end = str + strlen(str) - 1;
	while (end > str && isspace((unsigned char)*end))
		end--;
	*(end + 1) = '\0';

	return str;
}

/*
 * Build the path to the app_template.conf file.
 * Looks in the same directory as slurm.conf.
 */
static char *_get_conf_path(void)
{
	char *conf_path = NULL;
	char *slurm_conf = NULL;
	char *dir = NULL;

	slurm_conf = xstrdup(default_slurm_config_file);
	if (!slurm_conf) {
		slurm_conf = xstrdup("/etc/slurm/slurm.conf");
	}

	dir = xstrdup(slurm_conf);
	/* Find the last '/' to get directory */
	char *last_slash = strrchr(dir, '/');
	if (last_slash) {
		*(last_slash + 1) = '\0';
		xstrfmtcat(conf_path, "%s%s", dir, APP_TEMPLATE_CONF);
	} else {
		conf_path = xstrdup(APP_TEMPLATE_CONF);
	}

	xfree(slurm_conf);
	xfree(dir);
	return conf_path;
}

/*
 * Apply environment variables from the template to the job.
 * Format: env = KEY1=VAL1,KEY2=VAL2,...
 * Environment variables are always added (merged) into the job environment.
 */
static void _apply_env(slurm_opt_t *opt, const char *env_str)
{
	char *tmp, *save_ptr = NULL, *token;

	if (!env_str || !*env_str)
		return;

	tmp = xstrdup(env_str);
	token = strtok_r(tmp, ",", &save_ptr);
	while (token) {
		char *trimmed = _trim(token);
		char *eq = strchr(trimmed, '=');
		if (eq) {
			*eq = '\0';
			char *key = _trim(trimmed);
			char *val = _trim(eq + 1);
			if (key && *key) {
				if (opt->environment) {
					env_array_overwrite(&opt->environment,
							    key, val);
				}
				debug("app_template: setting env %s=%s",
				      key, val);
			}
		}
		token = strtok_r(NULL, ",", &save_ptr);
	}
	xfree(tmp);
}

extern int app_template_apply(slurm_opt_t *opt)
{
	FILE *fp = NULL;
	char *conf_path = NULL;
	char line[MAX_LINE_LEN];
	char *app_name = opt->app;
	bool in_section = false;
	bool found = false;

	if (!app_name || !*app_name) {
		return SLURM_SUCCESS;
	}

	conf_path = _get_conf_path();
	fp = fopen(conf_path, "r");
	if (!fp) {
		debug("app_template: config file not found: %s", conf_path);
		xfree(conf_path);
		return SLURM_SUCCESS;
	}

	debug("app_template: loading template for app '%s' from %s",
	      app_name, conf_path);

	while (fgets(line, sizeof(line), fp)) {
		char *trimmed = _trim(line);

		/* Skip empty lines and comments */
		if (!trimmed || *trimmed == '\0' || *trimmed == '#')
			continue;

		/* Check for section header [appname] */
		if (*trimmed == '[') {
			char *end = strchr(trimmed, ']');
			if (end) {
				*end = '\0';
				char *section_name = trimmed + 1;
				if (strcasecmp(section_name, app_name) == 0) {
					in_section = true;
					found = true;
				} else {
					if (in_section)
						break; /* Done with our section */
					in_section = false;
				}
			}
			continue;
		}

		if (!in_section)
			continue;

		/* Parse key = value */
		char *eq = strchr(trimmed, '=');
		if (!eq)
			continue;

		*eq = '\0';
		char *key = _trim(trimmed);
		char *value = _trim(eq + 1);

		if (!key || !*key || !value || !*value)
			continue;

		if (strcasecmp(key, "env") == 0) {
			_apply_env(opt, value);
		} else if (strcasecmp(key, "partition") == 0) {
			if (!opt->partition) {
				opt->partition = xstrdup(value);
				debug("app_template: setting partition=%s",
				      value);
			}
		} else if (strcasecmp(key, "gres") == 0) {
			if (!opt->gres) {
				opt->gres = xstrdup(value);
				debug("app_template: setting gres=%s", value);
			}
		} else if (strcasecmp(key, "ntasks") == 0) {
			if (!opt->ntasks_set) {
				opt->ntasks = atoi(value);
				opt->ntasks_set = true;
				debug("app_template: setting ntasks=%d",
				      opt->ntasks);
			}
		} else if (strcasecmp(key, "cpus_per_task") == 0) {
			if (!opt->cpus_set) {
				opt->cpus_per_task = atoi(value);
				opt->cpus_set = true;
				debug("app_template: setting cpus_per_task=%d",
				      opt->cpus_per_task);
			}
		} else if (strcasecmp(key, "mem_per_cpu") == 0) {
			if (opt->pn_min_memory == NO_VAL64) {
				opt->pn_min_memory = ((uint64_t)atoi(value))
						     | MEM_PER_CPU;
				debug("app_template: setting mem_per_cpu=%s",
				      value);
			}
		} else if (strcasecmp(key, "time_limit") == 0) {
			if (opt->time_limit == NO_VAL) {
				opt->time_limit = atoi(value);
				debug("app_template: setting time_limit=%d",
				      opt->time_limit);
			}
		} else {
			debug("app_template: unknown key '%s' in section [%s]",
			      key, app_name);
		}
	}

	fclose(fp);

	if (!found) {
		error("app_template: no template found for app '%s' in %s",
		      app_name, conf_path);
		xfree(conf_path);
		return SLURM_ERROR;
	}

	xfree(conf_path);
	return SLURM_SUCCESS;
}

#endif /* __METASTACK_NEW_APP_TEMPLATE */
