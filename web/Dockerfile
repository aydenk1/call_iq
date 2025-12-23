FROM node:20-slim

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

RUN mkdir -p /opt/web && cp -a node_modules /opt/web/

EXPOSE 3000

COPY web-entrypoint.sh /usr/local/bin/web-entrypoint.sh
RUN chmod 755 /usr/local/bin/web-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/web-entrypoint.sh"]
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
